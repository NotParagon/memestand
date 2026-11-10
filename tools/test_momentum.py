#!/usr/bin/env python3
"""Lifecycle labels from archived scores. Run: python3 tools/test_momentum.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import momentum as mo


def snap(**lists):
    out = {}
    for period, rows in lists.items():
        out[period] = [{"id": i, "rank": n, "score": s} for n, (i, s) in enumerate(rows, 1)]
    return out


def test_daily_score_wins_over_the_other_lists():
    day = snap(daily=[("a", 10)], weekly=[("a", 99), ("b", 4)], monthly=[("b", 7), ("c", 3)])
    assert mo.score_on_day(day) == {"a": 10.0, "b": 7.0, "c": 3.0}
    assert mo.score_on_day({"daily": [{"rank": 1, "removed": True, "score": 80}]}) == {}
    assert mo.score_on_day({"daily": [{"id": "x", "score": "nope"}]}) == {}
    assert mo.score_on_day(None) == {}


def test_status_labels_match_the_window_rules():
    assert mo.status_of([None, None, 10], seen_before=False) == "New"
    assert mo.status_of([None, None, 10], seen_before=True) == "Peaking"
    assert mo.status_of([10, 12, 14]) == "Rising"
    assert mo.status_of([10, 14, 14]) == "Peaking"
    assert mo.status_of([9, 9, 9]) == "Peaking"
    assert mo.status_of([14, 12, 11]) == "Fading"
    assert mo.status_of([5, 8, 7]) == "Fading"
    assert mo.status_of([10, None, None], seen_before=False) == "Fading"
    assert mo.status_of([None, None, None], seen_before=True) == "Fading"
    assert mo.status_of([None, None, None], seen_before=False) is None
    assert mo.status_of([], seen_before=False) is None


def test_week_delta_needs_a_score_on_both_ends():
    assert mo.week_delta([None, 4, 10]) is None
    assert mo.week_delta([8, 9, None]) is None
    assert mo.week_delta([8, 9, 11]) == 3
    assert mo.week_delta([4, 9, 4]) == 0
    assert mo.week_delta([None, 9, None]) is None
    assert mo.week_delta([]) is None
    rows = [
        {"slug": "entered", "name": "Entered", "delta": None},
        {"slug": "left", "name": "Left", "delta": None},
        {"slug": "up", "name": "Up", "delta": 1.5},
        {"slug": "down", "name": "Down", "delta": -0.4},
    ]
    risers, fallers = mo.movers(rows)
    assert [r["slug"] for r in risers] == ["up"]
    assert [r["slug"] for r in fallers] == ["down"]


def test_movers_are_the_largest_gains_and_drops():
    rows = [
        {"slug": "up-small", "name": "Up", "delta": 1},
        {"slug": "up-big", "name": "Big", "delta": 12},
        {"slug": "flat", "name": "Flat", "delta": 0},
        {"slug": "down", "name": "Down", "delta": -3},
        {"slug": "gone", "name": "Gone", "delta": -20},
        {"slug": "gap", "name": "Gap", "delta": None},
    ]
    risers, fallers = mo.movers(rows, limit=1)
    assert [r["slug"] for r in risers] == ["up-big"]
    assert [r["slug"] for r in fallers] == ["gone"]
    assert mo.fmt_delta(12.0) == "+12"
    assert mo.fmt_delta(-3.24) == "-3.2"
    assert mo.fmt_score(76.8) == "76.8"


def test_sparkline_is_static_svg_and_breaks_on_gaps():
    svg = mo.sparkline([1, None, 3, 4])
    assert svg.startswith("<svg")
    assert "<script" not in svg
    assert svg.count("<polyline") == 1
    assert "<circle" in svg
    assert "no score" in svg
    assert mo.sparkline([None, None]) == ""
    assert mo.sparkline([]) == ""
    assert mo.sparkline([10]) == ""
    assert mo.sparkline([None, 10, None]) == ""
    assert mo.sparkline([4, 4]).startswith("<svg")


def main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"{len(fns)} tests passed")


if __name__ == "__main__":
    main()
