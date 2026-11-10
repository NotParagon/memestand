"""Lifecycle labels from archived momentum scores.

This does not rank memes and does not change a score. It only reads the score
already stored on each day's snapshot and describes the recent trend.

One score per meme per Pacific archive day: the daily-list score when the meme
is on that list, otherwise the highest score on the other lists that day.
A day with no row is a gap, not a zero.

The window is the last WINDOW archive days. Status uses only that window:

- New: the only score in the window is on the latest day, and the meme has no
  earlier archive score.
- Rising: the latest score is above the previous score in the window and is
  the high of the window.
- Peaking: the latest score is the high of the window and did not rise from
  the previous score in the window.
- Fading: the latest score is below the window high, or the meme is absent
  from the latest day after appearing earlier.
- No label when the meme has no score in the window and none before it.

Week change compares the first day of the window with the latest day. Missing
at the start means the meme entered (change = the latest score). Missing at
the end means it left (change = minus the starting score). Missing at both
ends has no week change.
"""

WINDOW = 7


def _score(row):
    try:
        value = float(row["score"])
    except (KeyError, TypeError, ValueError):
        return None
    if value != value:  # NaN
        return None
    return value


def score_on_day(snapshot):
    """candidate id -> score for one archive snapshot. Removed rows are skipped."""
    if not isinstance(snapshot, dict):
        return {}
    best = {}
    on_daily = set()
    for row in snapshot.get("daily") or []:
        if not isinstance(row, dict) or row.get("removed") or not row.get("id"):
            continue
        value = _score(row)
        if value is None:
            continue
        best[row["id"]] = value
        on_daily.add(row["id"])
    for period in ("weekly", "monthly"):
        for row in snapshot.get(period) or []:
            if not isinstance(row, dict) or row.get("removed") or not row.get("id"):
                continue
            if row["id"] in on_daily:
                continue
            value = _score(row)
            if value is None:
                continue
            prev = best.get(row["id"])
            if prev is None or value > prev:
                best[row["id"]] = value
    return best


def status_of(series, seen_before=False):
    """One of New, Rising, Peaking, Fading, or None. See the module docstring."""
    if not series:
        return "Fading" if seen_before else None
    present = [(i, s) for i, s in enumerate(series) if s is not None]
    if not present:
        return "Fading" if seen_before else None
    latest = series[-1]
    if latest is None:
        return "Fading"
    if len(present) == 1 and not seen_before:
        return "New"
    peak = max(s for _, s in present)
    prev = present[-2][1] if len(present) >= 2 else None
    if prev is not None and latest > prev and latest >= peak:
        return "Rising"
    if latest >= peak:
        return "Peaking"
    return "Fading"


def week_delta(series):
    """Score change from the first window day to the latest. None when both are gaps."""
    if not series:
        return None
    start, end = series[0], series[-1]
    if start is None and end is None:
        return None
    if start is None:
        return end
    if end is None:
        return -start
    return end - start


def fmt_score(value):
    """76.8 stays 76.8. A whole number is written without a decimal."""
    value = float(value)
    rounded = round(value, 1)
    if abs(rounded - round(rounded)) < 1e-9:
        return str(int(round(rounded)))
    return f"{rounded:.1f}"


def fmt_delta(value):
    if value is None:
        return ""
    text = fmt_score(abs(value))
    if value > 0:
        return f"+{text}"
    if value < 0:
        return f"-{text}"
    return "0"


def movers(rows, limit=5):
    """Biggest score gains and drops. `rows` need slug, name, and delta."""
    up = [r for r in rows if r.get("delta") is not None and r["delta"] > 0]
    down = [r for r in rows if r.get("delta") is not None and r["delta"] < 0]
    up.sort(key=lambda r: (-r["delta"], (r.get("name") or "").lower(), r.get("slug") or ""))
    down.sort(key=lambda r: (r["delta"], (r.get("name") or "").lower(), r.get("slug") or ""))
    return up[:limit], down[:limit]


def sparkline(series, width=84, height=24):
    """Inline SVG polyline. Gaps break the line. No script and no external asset."""
    if not series:
        return ""
    present = [(i, s) for i, s in enumerate(series) if s is not None]
    if not present:
        return ""
    vals = [s for _, s in present]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    last = max(len(series) - 1, 1)

    def xy(i, s):
        x = 1.5 + (width - 3) * (i / last)
        y = 1.5 + (height - 3) * (1 - (s - lo) / span)
        return x, y

    runs, run, prev_i = [], [], None
    for i, s in present:
        if prev_i is not None and i != prev_i + 1 and run:
            runs.append(run)
            run = []
        run.append((i, s))
        prev_i = i
    if run:
        runs.append(run)
    parts = []
    for run in runs:
        if len(run) == 1:
            x, y = xy(*run[0])
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.7" fill="currentColor"/>')
        else:
            points = " ".join(f"{xy(i, s)[0]:.1f},{xy(i, s)[1]:.1f}" for i, s in run)
            parts.append(
                f'<polyline points="{points}" fill="none" stroke="currentColor" '
                'stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>'
            )
    label = "Momentum scores, oldest to newest: " + ", ".join(
        "no score" if s is None else fmt_score(s) for s in series)
    safe = (label.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;"))
    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'role="img" aria-label="{safe}">{"".join(parts)}</svg>'
    )
