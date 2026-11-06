#!/usr/bin/env python3
"""Edge cases for daily rank-history notes. Run: python3 tools/test_rank_history.py"""
import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import rank_history as rh

UTC = datetime.timezone.utc


def rows(*pairs, removed=()):
    daily = [{"id": i, "rank": r, "title": i} for i, r in pairs]
    for rank in removed:
        daily.append({"rank": rank, "removed": True, "title": "removed"})
    return {"daily": daily}


def texts(notes):
    return [n["text"] for n in notes]


def kinds(notes):
    return [n["kind"] for n in notes]


def test_first_day_has_no_notes():
    by = rh.ranks_by_day([("2026-11-01", rows(("alpha", 1), ("beta", 2)))])
    assert rh.history_notes("alpha", "2026-11-01", by, live=True) == []
    assert rh.history_notes("beta", "2026-11-01", by, live=False) == []
    assert "1 day" not in " ".join(texts(rh.history_notes("alpha", "2026-11-01", by)))


def test_unchanged_number_one_across_consecutive_days():
    snaps = [
        ("2026-11-01", rows(("alpha", 1), ("beta", 4))),
        ("2026-11-02", rows(("alpha", 1), ("beta", 4))),
        ("2026-11-03", rows(("alpha", 1), ("beta", 4))),
    ]
    by = rh.ranks_by_day(snaps)
    assert texts(rh.history_notes("alpha", "2026-11-02", by)) == [
        "Unchanged since yesterday", "2 days at #1"]
    assert texts(rh.history_notes("alpha", "2026-11-03", by)) == [
        "Unchanged since yesterday", "3 days at #1"]
    assert texts(rh.history_notes("beta", "2026-11-03", by)) == ["Unchanged since yesterday"]
    assert "days at #1" not in " ".join(texts(rh.history_notes("beta", "2026-11-03", by)))


def test_interruption_and_reentry():
    snaps = [
        ("2026-11-01", rows(("alpha", 1), ("beta", 2))),
        ("2026-11-02", rows(("beta", 1), ("gamma", 2))),  # alpha off the list; streak breaks
        ("2026-11-03", rows(("alpha", 1), ("beta", 3))),
    ]
    by = rh.ranks_by_day(snaps)
    back = rh.history_notes("alpha", "2026-11-03", by, live=True)
    assert texts(back) == ["New today"]
    assert "First time" not in texts(back)
    assert "days at #1" not in " ".join(texts(back))
    # beta stayed on the list, left #1, and is not #1 today
    assert texts(rh.history_notes("beta", "2026-11-03", by)) == ["Down 2 since yesterday"]


def test_number_one_returns_after_a_lower_rank():
    snaps = [
        ("2026-11-01", rows(("alpha", 1))),
        ("2026-11-02", rows(("alpha", 2), ("beta", 1))),
        ("2026-11-03", rows(("alpha", 1))),
    ]
    by = rh.ranks_by_day(snaps)
    notes = rh.history_notes("alpha", "2026-11-03", by)
    assert texts(notes) == ["Up 1 since yesterday"]
    assert kinds(notes) == ["up"]


def test_new_to_todays_list_is_not_the_same_as_first_ever():
    # "again" ranked on day 1, missed day 2, returned day 3: new to today's list, not first-ever.
    snaps = [
        ("2026-11-01", rows(("old", 1), ("again", 3))),
        ("2026-11-02", rows(("old", 2), ("debut", 5))),
        ("2026-11-03", rows(("old", 1), ("debut", 4), ("again", 6))),
    ]
    by = rh.ranks_by_day(snaps)
    debut = rh.history_notes("debut", "2026-11-02", by, live=True)
    assert texts(debut) == ["New today", "First time"]
    again = rh.history_notes("again", "2026-11-03", by, live=True)
    assert texts(again) == ["New today"]
    assert "First time" not in texts(again)
    assert kinds(debut) == ["new", "first"]
    assert kinds(again) == ["new"]


def test_movement_up_down_same():
    snaps = [
        ("2026-11-04", rows(("a", 8), ("b", 2), ("c", 5))),
        ("2026-11-05", rows(("a", 2), ("b", 8), ("c", 5))),
    ]
    by = rh.ranks_by_day(snaps)
    assert texts(rh.history_notes("a", "2026-11-05", by)) == ["Up 6 since yesterday"]
    assert texts(rh.history_notes("b", "2026-11-05", by)) == ["Down 6 since yesterday"]
    assert texts(rh.history_notes("c", "2026-11-05", by)) == ["Unchanged since yesterday"]


def test_archive_wording_does_not_say_today():
    snaps = [
        ("2026-11-04", rows(("a", 4), ("b", 1))),
        ("2026-11-05", rows(("a", 5), ("c", 2), ("b", 1))),
    ]
    by = rh.ranks_by_day(snaps)
    assert texts(rh.history_notes("a", "2026-11-05", by, live=False)) == ["Down 1 from the day before"]
    assert texts(rh.history_notes("c", "2026-11-05", by, live=False)) == ["New that day", "First time"]
    assert texts(rh.history_notes("b", "2026-11-05", by, live=False)) == [
        "Unchanged from the day before", "2 days at #1"]
    blob = " ".join(texts(rh.history_notes("c", "2026-11-05", by, live=False)))
    assert "New today" not in blob and "yesterday" not in blob


def test_missing_yesterday_does_not_fabricate_a_streak_or_a_debut():
    snaps = [
        ("2026-11-01", rows(("alpha", 1))),
        ("2026-11-02", rows(("alpha", 1))),
        # 2026-11-03 is missing
        ("2026-11-04", rows(("alpha", 1), ("newbie", 2))),
    ]
    by = rh.ranks_by_day(snaps)
    assert rh.history_notes("alpha", "2026-11-04", by) == []
    assert rh.history_notes("newbie", "2026-11-04", by) == []
    # the real streak still shows on the last day that has a previous file
    assert "2 days at #1" in texts(rh.history_notes("alpha", "2026-11-02", by))


def test_gap_blocks_first_time_but_not_a_real_pair_of_days_at_number_one():
    snaps = [
        ("2026-11-01", rows(("beta", 1))),
        # 2026-11-02 missing
        ("2026-11-03", rows(("beta", 1))),
        ("2026-11-04", rows(("beta", 2), ("alpha", 5))),
    ]
    by = rh.ranks_by_day(snaps)
    # yesterday exists, alpha never appears, but Nov 2 is missing: not "First time"
    assert texts(rh.history_notes("alpha", "2026-11-04", by)) == ["New today"]
    # Nov 3 and Nov 4 are a real consecutive pair for beta's movement; streak stopped on Nov 4
    # because beta is not #1. On Nov 3 the walk hits the missing Nov 2 and stays at 1.
    assert rh.history_notes("beta", "2026-11-03", by) == []
    assert texts(rh.history_notes("beta", "2026-11-04", by)) == ["Down 1 since yesterday"]


def test_streak_counts_only_a_contiguous_run():
    snaps = [
        ("2026-11-01", rows(("alpha", 2))),
        ("2026-11-02", rows(("alpha", 1))),
        ("2026-11-03", rows(("alpha", 1))),
        ("2026-11-04", rows(("alpha", 1))),
    ]
    by = rh.ranks_by_day(snaps)
    assert texts(rh.history_notes("alpha", "2026-11-04", by)) == [
        "Unchanged since yesterday", "3 days at #1"]
    assert "4 days" not in " ".join(texts(rh.history_notes("alpha", "2026-11-04", by)))


def test_later_days_do_not_change_an_earlier_day():
    early = [
        ("2026-11-01", rows(("alpha", 1))),
        ("2026-11-02", rows(("alpha", 1))),
    ]
    by = rh.ranks_by_day(early)
    before = texts(rh.history_notes("alpha", "2026-11-02", by))
    by["2026-11-05"] = {"alpha": 9, "other": 1}
    assert texts(rh.history_notes("alpha", "2026-11-02", by)) == before


def test_stable_slug_survives_a_new_candidate_id():
    slug_of = {"old-id": "same-meme", "new-id": "same-meme"}
    snaps = [
        ("2026-11-05", rows(("old-id", 1))),
        ("2026-11-06", rows(("new-id", 1))),
    ]
    by = rh.ranks_by_day(snaps, slug_of)
    assert texts(rh.history_notes("same-meme", "2026-11-06", by)) == [
        "Unchanged since yesterday", "2 days at #1"]
    bare = rh.ranks_by_day(snaps)
    # without the slug map the new id would look like a different meme
    assert texts(rh.history_notes("new-id", "2026-11-06", bare)) == ["New today", "First time"]


def test_duplicate_ids_same_day_keep_the_best_rank():
    slug_of = {"a": "meme", "b": "meme"}
    day = {"daily": [{"id": "a", "rank": 4}, {"id": "b", "rank": 1}, {"id": "a", "rank": 3}]}
    assert rh.daily_ranks(day["daily"], slug_of) == {"meme": 1}
    snaps = [
        ("2026-11-01", day),
        ("2026-11-02", rows(("a", 1))),
    ]
    by = rh.ranks_by_day(snaps, slug_of)
    assert "2 days at #1" in texts(rh.history_notes("meme", "2026-11-02", by))


def test_removed_rows_are_not_a_ranking():
    snaps = [
        ("2026-11-01", rows(removed=(1,))),
        ("2026-11-02", rows(("alpha", 1))),
    ]
    by = rh.ranks_by_day(snaps)
    assert texts(rh.history_notes("alpha", "2026-11-02", by)) == ["New today", "First time"]
    assert rh.meme_identity({"removed": True, "id": "alpha", "rank": 1}) is None
    assert rh.meme_identity({"id": "alpha", "rank": 1}, {"alpha": "slug"}) == "slug"


def test_hourly_overwrite_does_not_add_a_day():
    morning = ("2026-11-06", rows(("alpha", 1), ("beta", 2)))
    evening = ("2026-11-06", rows(("beta", 1), ("alpha", 2)))
    snaps = [("2026-11-05", rows(("alpha", 1), ("beta", 3))), morning, evening]
    by = rh.ranks_by_day(snaps)
    assert list(by) == ["2026-11-05", "2026-11-06"]
    assert by["2026-11-06"] == {"beta": 1, "alpha": 2}
    assert texts(rh.history_notes("alpha", "2026-11-06", by)) == ["Down 1 since yesterday"]
    assert "days at #1" not in " ".join(texts(rh.history_notes("alpha", "2026-11-06", by)))
    assert texts(rh.history_notes("beta", "2026-11-06", by)) == ["Up 2 since yesterday"]
    # same ranks repeated across hours stay one day at the head of a 2-day streak
    held = rh.ranks_by_day([
        ("2026-11-05", rows(("alpha", 1))),
        ("2026-11-06", rows(("alpha", 1))),
        ("2026-11-06", rows(("alpha", 1))),
    ])
    assert texts(rh.history_notes("alpha", "2026-11-06", held)) == [
        "Unchanged since yesterday", "2 days at #1"]


def test_pacific_midnight_splits_days_and_hourly_stamps_do_not():
    morning = datetime.datetime(2026, 11, 6, 14, 0, tzinfo=UTC)    # 6:00 AM PST
    evening = datetime.datetime(2026, 11, 7, 4, 30, tzinfo=UTC)    # 8:30 PM PST, same date
    before = datetime.datetime(2026, 11, 7, 7, 59, tzinfo=UTC)     # 11:59 PM PST
    after = datetime.datetime(2026, 11, 7, 8, 0, tzinfo=UTC)       # 12:00 AM PST Nov 7
    assert rh.pacific_day(morning) == datetime.date(2026, 11, 6)
    assert rh.pacific_day(evening) == datetime.date(2026, 11, 6)
    assert rh.pacific_day(before) == datetime.date(2026, 11, 6)
    assert rh.pacific_day(after) == datetime.date(2026, 11, 7)
    day = rh.pacific_day(morning).isoformat()
    assert day == rh.pacific_day(evening).isoformat() == rh.pacific_day(before).isoformat()
    snaps = [
        (day, rows(("alpha", 1))),
        (rh.pacific_day(evening).isoformat(), rows(("alpha", 1))),
        (rh.pacific_day(after).isoformat(), rows(("alpha", 1))),
    ]
    by = rh.ranks_by_day(snaps)
    assert sorted(by) == ["2026-11-06", "2026-11-07"]
    got = texts(rh.history_notes("alpha", "2026-11-07", by))
    assert got == ["Unchanged since yesterday", "2 days at #1"]
    try:
        rh.pacific_day(datetime.datetime(2026, 11, 6, 12, 0))
    except ValueError:
        pass
    else:
        raise AssertionError("naive datetimes must not be treated as Pacific")


def test_missing_identity_and_bad_day_are_empty():
    by = rh.ranks_by_day([("2026-11-02", rows(("alpha", 1)))])
    assert rh.history_notes("", "2026-11-02", by) == []
    assert rh.history_notes("alpha", "2026-11-03", by) == []
    assert rh.history_notes("nope", "2026-11-02", by) == []
    assert rh.history_notes("alpha", "yesterday", by) == []
    assert rh.daily_ranks([{"id": "a", "rank": "nope"}, {"id": "b"}]) == {}


def main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"{len(fns)} tests passed")


if __name__ == "__main__":
    main()
