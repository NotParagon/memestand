#!/usr/bin/env python3
"""Pacific "updated" stamp, the build guard, and stable datePublished.

Run: python3 tools/test_stamp.py
"""
import datetime
import io
import json
import os
import pathlib
import subprocess
import sys
from contextlib import redirect_stdout
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import build
import stamp

ROOT = pathlib.Path(__file__).resolve().parent.parent
PT = ZoneInfo("America/Los_Angeles")
UTC = datetime.timezone.utc


def test_format_stamp_converts_utc_to_pacific_and_not_a_fixed_offset():
    # 11:13 UTC on a standard-time day is 3:13 AM Pacific, not 11:13 with -08:00 glued on.
    winter = datetime.datetime(2026, 11, 14, 11, 13, tzinfo=UTC)
    assert stamp.format_stamp(winter) == "2026-11-14T03:13-08:00"
    # The same wall clock in July is PDT, -07:00. A hard-coded -08:00 would be wrong.
    summer = datetime.datetime(2026, 7, 14, 19, 0, tzinfo=UTC)
    assert stamp.format_stamp(summer) == "2026-07-14T12:00-07:00"
    naive = datetime.datetime(2026, 11, 14, 11, 13)
    try:
        stamp.pacific_now(naive)
    except ValueError:
        return
    raise AssertionError("naive datetimes must not be treated as Pacific")


def test_resolve_stamp_keeps_skew_and_rejects_future_or_naive():
    now = datetime.datetime(2026, 11, 14, 3, 13, tzinfo=PT)
    kept, reason = stamp.resolve_stamp("2026-11-14T03:23-08:00", now)
    assert reason is None
    assert kept.isoformat(timespec="minutes") == "2026-11-14T03:23-08:00"
    # A correct UTC instant is the same moment and is kept.
    same, reason = stamp.resolve_stamp("2026-11-14T11:13:00+00:00", now)
    assert reason is None
    assert same.astimezone(PT) == now
    future, reason = stamp.resolve_stamp("2026-11-14T11:13-08:00", now)
    assert reason and "future" in reason
    assert stamp.format_stamp(future) == "2026-11-14T03:13-08:00"
    # 11 minutes ahead is past the 10-minute slack. Exactly 10 minutes is not.
    ten, reason = stamp.resolve_stamp("2026-11-14T03:23:00-08:00", now)
    assert reason is None and ten.hour == 3 and ten.minute == 23
    eleven, reason = stamp.resolve_stamp("2026-11-14T03:24-08:00", now)
    assert reason and "future" in reason
    for bad in ("2026-11-14T11:13", "2026-11-14", "", None, "not-a-date"):
        replaced, reason = stamp.resolve_stamp(bad, now)
        assert reason and "not parseable" in reason, bad
        assert stamp.format_stamp(replaced) == "2026-11-14T03:13-08:00"


def test_bump_writes_pacific_time_and_leaves_the_rest_of_the_file():
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        path = pathlib.Path(directory) / "memes.json"
        path.write_text(
            '{\n  "updated": "1999-01-01T00:00-08:00",\n  "daily": [{"id": "keep", "notes": "same"}]\n}\n'
        )
        now = datetime.datetime(2026, 11, 14, 11, 13, tzinfo=UTC)
        got = stamp.bump(path, now=now)
        assert got == "2026-11-14T03:13-08:00"
        text = path.read_text()
        assert text.startswith('{\n  "updated": "2026-11-14T03:13-08:00"')
        assert '"id": "keep"' in text and '"notes": "same"' in text
        doc = json.loads(text)
        assert doc["updated"] == got
        assert doc["daily"] == [{"id": "keep", "notes": "same"}]
        # Writing the same minute does not touch the file.
        before = path.stat().st_mtime_ns
        stamp.bump(path, now=now)
        assert path.stat().st_mtime_ns == before


def test_cli_uses_pacific_time_even_when_tz_is_utc():
    import tempfile
    script = ROOT / "tools" / "stamp.py"
    body = '{ "updated": "1999-01-01T00:00-08:00", "daily": [] }\n'
    with tempfile.TemporaryDirectory() as directory:
        directory = pathlib.Path(directory)
        def run(tz):
            path = directory / (tz.replace("/", "_") + ".json")
            path.write_text(body)
            env = os.environ.copy()
            env["TZ"] = tz
            proc = subprocess.run(
                [sys.executable, str(script), str(path)],
                env=env, capture_output=True, text=True, check=True)
            return proc.stdout.strip(), json.loads(path.read_text())["updated"]
        utc_out, utc_file = run("UTC")
        other_out, other_file = run("Pacific/Auckland")
        assert utc_out == utc_file and other_out == other_file
        delta = abs((stamp.parse_stamp(utc_out) - stamp.parse_stamp(other_out)).total_seconds())
        assert delta <= 60
        # Not the UTC wall clock labeled with a hard-coded Pacific offset.
        utc_now = datetime.datetime.now(UTC).replace(second=0, microsecond=0)
        bogus = utc_now.strftime("%Y-%m-%dT%H:%M") + "-08:00"
        assert utc_out != bogus
        assert stamp.parse_stamp(utc_out).utcoffset() in (
            datetime.timedelta(hours=-8), datetime.timedelta(hours=-7))


def test_guard_replaces_future_and_unparseable_and_warns():
    now = datetime.datetime(2026, 11, 14, 3, 13, tzinfo=PT)
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        path = pathlib.Path(directory) / "memes.json"
        path.write_text('{\n  "updated": "2026-11-14T11:13-08:00",\n  "daily": [{"id": "a"}]\n}\n')
        data = json.loads(path.read_text())
        buf = io.StringIO()
        with redirect_stdout(buf):
            got = build.apply_updated_guard(data, now=now, persist_path=path)
        warning = buf.getvalue()
        assert warning.startswith("! WARNING:")
        assert "future" in warning
        assert "2026-11-14T03:13-08:00" in warning
        assert data["updated"] == "2026-11-14T03:13-08:00"
        assert data["daily"] == [{"id": "a"}]
        assert got.isoformat(timespec="minutes") == "2026-11-14T03:13-08:00"
        saved = json.loads(path.read_text())
        assert saved["updated"] == "2026-11-14T03:13-08:00"
        assert saved["daily"] == [{"id": "a"}]

        naive = {"updated": "2026-11-14T11:13", "daily": []}
        buf = io.StringIO()
        with redirect_stdout(buf):
            build.apply_updated_guard(naive, now=now)
        assert naive["updated"] == "2026-11-14T03:13-08:00"
        assert "not parseable" in buf.getvalue()

        garbage = {"updated": "nope"}
        buf = io.StringIO()
        with redirect_stdout(buf):
            build.apply_updated_guard(garbage, now=now)
        assert garbage["updated"] == "2026-11-14T03:13-08:00"
        assert "not parseable" in buf.getvalue()

        close = {"updated": "2026-11-14T03:20-08:00"}
        buf = io.StringIO()
        with redirect_stdout(buf):
            kept = build.apply_updated_guard(close, now=now)
        assert buf.getvalue() == ""
        assert close["updated"] == "2026-11-14T03:20-08:00"
        assert kept.isoformat(timespec="minutes") == "2026-11-14T03:20-08:00"


def test_future_stamp_does_not_freeze_today_and_yesterday_stays_locked():
    # The Nov 14 incident: 3:13 AM PT stored as 11:13-08:00. A 4:05 AM run must
    # still replace today's file. The live archive day stays Nov 14.
    now = datetime.datetime(2026, 11, 14, 4, 5, tzinfo=PT)
    existing = {"updated": "2026-11-14T11:13-08:00", "daily": [{"id": "a"}]}
    incoming = {"updated": "2026-11-14T04:05-08:00", "daily": [{"id": "a", "notes": "new"}]}
    assert build.snapshot_replaces(existing, incoming, now=now) is True
    assert build.archive_day_for(stamp.parse_stamp(incoming["updated"])) == "2026-11-14"
    # A UTC wall clock that crosses midnight must not open tomorrow's archive.
    evening = datetime.datetime(2026, 11, 14, 19, 0, tzinfo=PT)
    crossed = {"updated": "2026-11-15T03:00-08:00"}
    buf = io.StringIO()
    with redirect_stdout(buf):
        corrected = build.apply_updated_guard(crossed, now=evening)
    assert "future" in buf.getvalue()
    assert build.archive_day_for(corrected) == "2026-11-14"
    assert crossed["updated"] == "2026-11-14T19:00-08:00"
    # Through the Pacific day, a later real stamp replaces. An equal stamp does not.
    early = {"updated": "2026-11-14T06:00-08:00"}
    later = {"updated": "2026-11-14T19:00-08:00"}
    assert build.snapshot_replaces(early, later, now=evening) is True
    assert build.snapshot_replaces(later, later, now=evening) is False
    # The next Pacific morning is a new file. Yesterday is not that day, so the
    # writer does not open it (snapshots only writes TODAY).
    morning = datetime.datetime(2026, 11, 15, 6, 0, tzinfo=PT)
    assert build.archive_day_for(morning) == "2026-11-15"
    assert build.archive_day_for(morning) != "2026-11-14"
    assert build.snapshot_replaces(later, {"updated": "2026-11-15T06:00-08:00"}, now=morning) is True


def test_date_published_stays_on_the_first_seen_day_and_not_after_modified():
    checked = "2026-11-13T06:40:00-08:00"
    early = datetime.datetime.fromisoformat("2026-11-13T06:12:00-08:00")
    later = datetime.datetime.fromisoformat("2026-11-13T23:11:00-08:00")
    # Two builds the same first day: the archive clock moves, published must not.
    p1, m1 = build.publication_times("2026-11-13", checked, early)
    p2, m2 = build.publication_times("2026-11-13", checked, later)
    assert p1 == p2
    assert p1.isoformat(timespec="seconds") == "2026-11-13T00:00:00-08:00"
    assert m1 == m2
    assert m1.isoformat(timespec="seconds") == "2026-11-13T06:40:00-08:00"
    assert p1 <= m1
    # No review time: modified may follow the snapshot. Published stays put.
    p3, m3 = build.publication_times("2026-11-13", None, early)
    p4, m4 = build.publication_times("2026-11-13", None, later)
    assert p3 == p4 == p1
    assert m3 == early and m4 == later
    assert p3 <= m3 and p4 <= m4
    # The earlier of the written day and the first archive day wins.
    assert build.first_seen_day("2026-11-13", "2026-11-14") == datetime.date(2026, 11, 13)
    # A review before that day pulls published back so it is not later.
    p5, m5 = build.publication_times("2026-11-13", "2026-11-12T22:00:00-08:00", later)
    assert p5 == m5
    assert p5 <= m5
    assert p5.isoformat(timespec="seconds") == "2026-11-12T22:00:00-08:00"
    # Summer midnight uses the daylight offset, not a hard-coded -08:00.
    summer_mod = datetime.datetime(2026, 7, 4, 18, 0, tzinfo=PT)
    p6, m6 = build.publication_times("2026-07-04", "2026-07-04T15:00:00-07:00", summer_mod)
    assert p6.isoformat(timespec="seconds") == "2026-07-04T00:00:00-07:00"
    assert p6 <= m6


def test_rank_module_uses_the_shared_stamp():
    src = (ROOT / "tools" / "rank.py").read_text()
    assert 'out = {"updated": format_stamp()}' in src
    assert "datetime.now()" not in src
    assert "ZoneInfo" not in src


def main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"{len(fns)} tests passed")


if __name__ == "__main__":
    main()
