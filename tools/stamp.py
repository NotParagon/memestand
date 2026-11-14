#!/usr/bin/env python3
"""Write data/memes.json "updated" as the real America/Los_Angeles time.

Light hourly runs bump the stamp without re-ranking:

    python3 tools/stamp.py

The value is the current instant as a timezone-aware UTC now(), converted to
America/Los_Angeles. It is never the machine's naive local clock with a
hard-coded -08:00 glued on. That mistake labels the UTC wall clock as Pacific
(so 3:13 AM PT becomes 11:13-08:00) and freezes today's archive, because a
later real run looks older than the future stamp.

PST is -08:00 and PDT is -07:00; ZoneInfo picks the one in effect.
An optional path argument writes a different JSON file (tests). The default
is this repo's data/memes.json, independent of the working directory.
"""
import datetime
import re
import sys
import pathlib
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
ROOT = pathlib.Path(__file__).resolve().parent.parent
MEMES = ROOT / "data" / "memes.json"
FUTURE_SLACK = datetime.timedelta(minutes=10)
_UPDATED = re.compile(r'("updated"\s*:\s*")[^"]*"')


def pacific_now(now=None):
    """Current time in America/Los_Angeles.

    `now`, when passed, must already be timezone-aware. It is converted, not
    reinterpreted: a UTC instant stays the same instant.
    """
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
        raise ValueError("pacific_now requires a timezone-aware datetime")
    return now.astimezone(PT)


def format_stamp(when=None):
    """Minute-precision ISO timestamp with the Pacific offset, matching memes.json."""
    dt = pacific_now(when).replace(second=0, microsecond=0)
    return dt.isoformat(timespec="minutes")


def parse_stamp(value):
    """Aware America/Los_Angeles datetime, or ValueError.

    Naive strings are rejected. Treating them as local time, or appending
    -08:00 by hand, is how a UTC clock was stored as Pacific.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("empty timestamp")
    dt = datetime.datetime.fromisoformat(value.strip())
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError("naive timestamp")
    return dt.astimezone(PT)


def resolve_stamp(value, now=None):
    """Return (dt, reason).

    reason is None when `value` is a usable timestamp at or before 10 minutes
    ahead of real Pacific now. Otherwise dt is that now, truncated to the
    minute, and reason says why the stored value was rejected.
    """
    now_pt = pacific_now(now).replace(second=0, microsecond=0)
    try:
        dt = parse_stamp(value)
    except (TypeError, ValueError):
        return now_pt, "is not parseable"
    if dt - now_pt > FUTURE_SLACK:
        return now_pt, "is more than 10 minutes in the future"
    return dt, None


def set_updated(path, fresh):
    """Replace the first "updated" string in a JSON file. Other bytes stay put."""
    path = pathlib.Path(path)
    text = path.read_text()
    new_text, n = _UPDATED.subn(lambda m: m.group(1) + fresh + '"', text, count=1)
    if n != 1:
        raise ValueError(f"no updated field in {path}")
    if new_text != text:
        path.write_text(new_text)
    return fresh


def bump(path=None, now=None):
    """Set "updated" to the current Pacific time. Returns the stamp string."""
    path = pathlib.Path(path) if path else MEMES
    return set_updated(path, format_stamp(now))


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    path = pathlib.Path(args[0]) if args else MEMES
    if len(args) > 1:
        print("usage: python3 tools/stamp.py [path]", file=sys.stderr)
        return 2
    try:
        print(bump(path))
    except (OSError, ValueError) as ex:
        print(f"! WARNING: {ex}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
