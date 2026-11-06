"""History notes for one Pacific day's daily top 10.

Notes come only from archived daily rankings (one list per Pacific calendar day)
and a stable meme identity. An hourly rebuild of the same day replaces that day's
list; it does not add a day. A missing archive day is a gap: it is not a ranking,
it does not prove that a meme is new, and it stops a #1 streak.

Identity is the meme-page slug when `slug_of` maps the candidate id, otherwise
the candidate id. Callers pass dates already resolved in America/Los_Angeles.
`pacific_day` is that conversion for tests and for any timestamp a caller has.
"""
import datetime
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")

_TITLES = {
    "new": "On this day's daily top 10, not on the previous Pacific day's list",
    "first": "No earlier archived daily top 10 includes this meme",
    "up": "Better daily rank than the previous Pacific day",
    "down": "Worse daily rank than the previous Pacific day",
    "same": "Same daily rank as the previous Pacific day",
    "streak": "Daily #1 on each consecutive archived Pacific day ending this day",
}


def pacific_day(when):
    """Calendar date in America/Los_Angeles. `when` must be an aware datetime or a date."""
    if isinstance(when, datetime.datetime):
        if when.tzinfo is None:
            raise ValueError("pacific_day requires a timezone-aware datetime")
        return when.astimezone(PT).date()
    if isinstance(when, datetime.date):
        return when
    raise TypeError("pacific_day expects a date or datetime")


def meme_identity(meme, slug_of=None):
    """Stable id for a daily row. Removed rows and rows without an id have none."""
    if not meme or meme.get("removed") or not meme.get("id"):
        return None
    mid = meme["id"]
    if slug_of is None:
        return mid
    mapped = slug_of(mid) if callable(slug_of) else slug_of.get(mid)
    return mapped or mid


def daily_ranks(rows, slug_of=None):
    """identity -> best (lowest) rank. Later duplicate identities keep the better rank."""
    out = {}
    for meme in rows or []:
        ident = meme_identity(meme, slug_of)
        if not ident:
            continue
        try:
            rank = int(meme["rank"])
        except (KeyError, TypeError, ValueError):
            continue
        if rank < 1:
            continue
        prev = out.get(ident)
        if prev is None or rank < prev:
            out[ident] = rank
    return out


def ranks_by_day(snapshots, slug_of=None):
    """(YYYY-MM-DD, snapshot) pairs -> {day: {identity: rank}}.

    A repeated date replaces the earlier list. That is the hourly refresh of one
    Pacific day, not a new day.
    """
    out = {}
    for day, snap in snapshots:
        datetime.date.fromisoformat(day)
        rows = snap.get("daily") if isinstance(snap, dict) else None
        out[day] = daily_ranks(rows, slug_of)
    return out


def _dates(by_day):
    found = []
    for key in by_day:
        try:
            found.append(datetime.date.fromisoformat(key))
        except (TypeError, ValueError):
            continue
    return sorted(set(found))


def _continuous(dates):
    """True when `dates` is a non-empty run of consecutive calendar days."""
    if not dates:
        return False
    return (dates[-1] - dates[0]).days == len(dates) - 1


def _note(kind, text):
    return {"kind": kind, "text": text, "title": _TITLES[kind]}


def _days_at_one(identity, day, by_day):
    """Consecutive archived days ending on `day` where `identity` was daily #1.

    The walk is one calendar day at a time. A missing file or any other rank stops it.
    """
    d = datetime.date.fromisoformat(day)
    n = 0
    while True:
        ranks = by_day.get(d.isoformat())
        if not ranks or ranks.get(identity) != 1:
            break
        n += 1
        d -= datetime.timedelta(days=1)
    return n


def history_notes(identity, day, by_day, *, live=True):
    """Notes for `identity` on `day`.

    `by_day` maps ISO dates (including `day`, and usually later days) to rank maps.
    Later days are ignored. `live` selects homepage wording ("New today", "since
    yesterday"); archive pages pass live=False ("New that day", "from the day before").

    Returns a list of {kind, text, title}. Empty when this is the first archived day,
    yesterday's file is missing, or the identity is not on `day`'s list. "First time"
    is only added when the identity is absent from every earlier daily list and the
    archive has no gap from its first day through yesterday. A reentry is "New today"
    and is not "First time". "N days at #1" starts at 2.
    """
    if not identity or not by_day or day not in by_day or identity not in by_day[day]:
        return []
    try:
        current = datetime.date.fromisoformat(day)
    except (TypeError, ValueError):
        return []
    notes = []
    prior = [d for d in _dates(by_day) if d < current]
    yesterday = current - datetime.timedelta(days=1)
    ykey = yesterday.isoformat()
    if prior and ykey in by_day:
        yranks = by_day[ykey]
        if identity in yranks:
            delta = yranks[identity] - by_day[day][identity]
            if delta > 0:
                tail = "since yesterday" if live else "from the day before"
                notes.append(_note("up", f"Up {delta} {tail}"))
            elif delta < 0:
                tail = "since yesterday" if live else "from the day before"
                notes.append(_note("down", f"Down {-delta} {tail}"))
            else:
                text = "Unchanged since yesterday" if live else "Unchanged from the day before"
                notes.append(_note("same", text))
        else:
            notes.append(_note("new", "New today" if live else "New that day"))
            seen = any(identity in by_day.get(d.isoformat(), {}) for d in prior)
            if not seen and _continuous(prior):
                notes.append(_note("first", "First time"))
    n = _days_at_one(identity, day, by_day)
    if n >= 2:
        notes.append(_note("streak", f"{n} days at #1"))
    return notes
