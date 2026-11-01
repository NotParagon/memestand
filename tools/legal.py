"""Legal / content-safety rules shared by tools/rank.py and build.py.  See UPDATE.md "Legal rules".

- Blocklist (data/blocklist.json): takedown / DMCA removals. A blocked item is never ranked, is replaced by a
  "removed" placeholder on every page (archives included), is scrubbed from data/archive/*.json, and its local
  thumbnail is deleted.
- Content exclusions: candidates flagged nsfw / hate / minor / etc. are never ranked.
- Headline neutrality: a headline that states an allegation about a person (affair, fraud, crime...) must be
  attributed ("per KYM", "alleged", "memes about...") or carry "headline_reviewed": true, or it is excluded.
"""
import json, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
BLOCKLIST = ROOT / "data" / "blocklist.json"

# ---------------------------------------------------------------- blocklist
def load_blocklist():
    if not BLOCKLIST.exists(): return []
    return json.loads(BLOCKLIST.read_text()).get("entries", [])

def _norm(u):
    return re.sub(r"^https?://(www\.|old\.|m\.|mobile\.)?", "", (u or "").strip().lower()).split("?")[0].rstrip("/")

def _urls(item):
    us = [item.get("source_url"), item.get("image_url")] + [a.get("url") for a in (item.get("also") or [])]
    return {_norm(u) for u in us if u}

def blocked_by(item, entries):
    """Return the matching blocklist entry, or None. Entries match on id, any URL (source/image/also), or a
    case-insensitive title substring."""
    urls, title = _urls(item), (item.get("title") or "").lower()
    for b in entries:
        if b.get("id") and b["id"] == item.get("id"): return b
        if any(_norm(u) in urls for u in ([b.get("url")] if b.get("url") else []) + b.get("urls", [])): return b
        if b.get("title_contains") and b["title_contains"].lower() in title: return b
    return None

# ---------------------------------------------------------------- content policy
EXCLUDE_FLAGS = {"nsfw", "sexual", "explicit", "hate", "demeaning", "harassment", "minor", "minors", "graphic",
                 "gore", "self-harm", "doxxing", "private-person", "defamatory", "blocked"}
# Hard-excluded words in title / card text / notes (whole-word, case-insensitive).
HARD_TERMS = r"nsfw|nude|nudes|nudity|porn\w*|onlyfans|hentai|gore|beheading|suicide|self[- ]harm|underage|loli|doxx?(ed|ing)?|leaked nudes"
# Words that suggest a child may be the subject: excluded unless "minor_reviewed": true (adult confirmed or no child shown).
MINOR_TERMS = r"child|children|kid|kids|toddler|baby|babies|teen|teens|teenager|minor|minors|schoolgirl|schoolboy|middle school|high school|\d{1,2}[- ]year[- ]old"
# Allegation words that need attribution when a real person is the subject.
ALLEGATION_TERMS = r"affair|cheat\w*|scandal|fraud\w*|scam\w*|arrest\w*|charged|crime|criminal|convicted|rape\w*|assault\w*|abuse\w*|racist|pedo\w*|groom\w*|lied|liar|stole|steal\w*|murder\w*|killed|overdose\w*|drunk|addict\w*|corrupt\w*|bribe\w*|sued|lawsuit|harass\w*|predator"
ATTRIBUTION = r"\bper\b|alleg\w*|accus\w*|according to|reportedly|claims?\b|memes? about|jokes?\b|joking|parody|satire|roast\w*"

def _has(pat, text): return re.search(rf"\b({pat})\b", text or "", re.I)

def exclusion_reason(c):
    """Why a candidate must not be ranked (str), or None if it may be ranked."""
    flags = {f.lower() for f in c.get("flags", [])}
    if flags & EXCLUDE_FLAGS: return f"flagged {sorted(flags & EXCLUDE_FLAGS)}"
    if not c.get("source_url") or not c.get("source_name"): return "no source / attribution"
    text = " ".join(str(c.get(k) or "") for k in ("title", "card_text", "notes"))
    m = _has(HARD_TERMS, text)
    if m: return f"content term '{m.group(0)}'"
    m = _has(MINOR_TERMS, text)
    if m and not c.get("minor_reviewed"): return f"possible minor ('{m.group(0)}'): confirm and set minor_reviewed: true"
    t = " ".join(str(c.get(k) or "") for k in ("title", "card_text"))
    m = _has(ALLEGATION_TERMS, t)
    if m and not _has(ATTRIBUTION, t) and not c.get("headline_reviewed"):
        return (f"headline asserts '{m.group(0)}' without attribution: rewrite neutrally "
                f"('memes about...', 'per KYM', 'alleged') or set headline_reviewed: true after checking")
    return None

# ---------------------------------------------------------------- credit line
def default_credit(c, reddit_authors=None):
    if c.get("credit"): return c["credit"]
    src, name = c.get("source_url") or "", c.get("source_name") or ""
    if "reddit.com" in src:
        sub = re.search(r"/r/([^/]+)/", src)
        au = (reddit_authors or {}).get(src)
        who = au.lstrip("/") if au else "a Reddit user"
        return f"posted by {who}" + (f" on r/{sub.group(1)}" if sub else " on Reddit")
    m = re.match(r"X / (@\w+)", name)
    if m: return f"posted by {m.group(1)} on X"
    if "knowyourmeme.com" in src: return "image via Know Your Meme; original creators as documented there"
    return f"via {name}"
