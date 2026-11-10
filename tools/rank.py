#!/usr/bin/env python3
"""Score candidates, pick Top 10 per period, download thumbnails, write data/memes.json.

Usage:  python3 tools/rank.py [--no-images]

Scoring rubric (cross-platform virality evidence, documented in UPDATE.md "Ranking method"):
  Six sources: X, TikTok, Instagram, Reddit (r/memes, r/dankmemes), YouTube, Know Your Meme.
  1. Per-source reach score, each on its own scale so one platform's huge raw counts don't dominate
     (calibrated so a very big post on each platform lands near 70; each capped at 75):
       X          10*log10(views)           or 10*log10(likes*10) if only likes are known
       TikTok     10*log10(views) - 5       (TikTok plays are cheap: 30M -> ~70)
       Instagram  10*log10(likes*10) - 5    (logged-out pages show likes, not plays; likes x10 ~ plays)
       YouTube    10*log10(views) + 5       (meme videos earn fewer views: 2M -> ~68)
       Reddit     feed position: r/memes 62-2*(rank-1), r/dankmemes 60-2*(rank-1)
     Evidence lives in ev.x / ev.tiktok / ev.instagram / ev.youtube / ev.reddit (see UPDATE.md).
     Legacy ev.peak_views / ev.peak_likes (no ev.x) are read as X.
  2. score = best reach + 0.10 * 2nd best + 0.05 * 3rd best
  3. +3 per extra source with confirmed evidence (of the six; Know Your Meme counts), max +12
  4. +3 picked in a KYM editorial / Meme-of-the-Month poll   +5 X News trending story
     +5 KYM entry page views >= 50,000

Legal rules (tools/legal.py, UPDATE.md "Legal rules"):
  - data/blocklist.json entries (takedowns) are never ranked and are dropped from candidates.json.
  - flagged / NSFW / hate / possible-minor / unattributed-allegation candidates are excluded (reason printed).
  - thumbnails: max 400px, EXIF/metadata stripped, re-checked on every run (archive images too).
  - per-candidate "image_policy": "local" (default: small local thumbnail), "hotlink" (show image_url from
    the source's own CDN, no local copy), or "none" (text card that links to the source).
"""
import json, math, sys, pathlib, subprocess, io, datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from legal import load_blocklist, blocked_by, exclusion_reason, default_credit
from post_cards import local_image as post_card_image
from safe_url import safe_url

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA, IMG = ROOT / "data", ROOT / "images"
PERIODS = ["daily", "weekly", "monthly"]
MAX_PX = 400            # thumbnail cap (longest side), all positions incl. the top story
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

SOURCES = ["X", "TikTok", "Instagram", "Reddit", "YouTube", "Know Your Meme"]
ALIASES = {"KYM": "Know Your Meme", "IG": "Instagram", "Twitter": "X"}
CAP = 75
MIN_YT = 10_000          # a YouTube video below this many views doesn't count as spread

def _lg(n): return 10 * math.log10(n) if n and n > 0 else None

def reach(ev):
    """Per-source normalized reach scores {source: score} (see the rubric above)."""
    r = {}
    x = ev.get("x") or ({"views": ev.get("peak_views"), "likes": ev.get("peak_likes")}
                        if (ev.get("peak_views") or ev.get("peak_likes")) else None)
    if x:
        v = [a for a in (_lg(x.get("views")), _lg((x.get("likes") or 0) * 10)) if a]
        if v: r["X"] = max(v)
    t = ev.get("tiktok")
    if t:
        v = _lg(t.get("views")) or _lg((t.get("likes") or 0) * 10)
        if v: r["TikTok"] = v - 5
    ig = ev.get("instagram")
    if ig:
        v = _lg(ig.get("views")) or _lg((ig.get("likes") or 0) * 10)
        if v: r["Instagram"] = v - 5
    yt = ev.get("youtube")
    if yt and (yt.get("views") or 0) >= MIN_YT: r["YouTube"] = _lg(yt["views"]) + 5
    rd = ev.get("reddit")
    if rd: r["Reddit"] = (62 if rd["sub"] == "memes" else 60) - 2 * (rd["rank"] - 1)
    return {k: min(CAP, v) for k, v in r.items()}

def sources(ev):
    """Sources with confirmed evidence: anything with a reach score, KYM documentation, or a listed platform."""
    found = set(reach(ev))
    if ev.get("kym"): found.add("Know Your Meme")
    for p in ev.get("platforms", []):
        p = ALIASES.get(p, p)
        if p in SOURCES and (p != "YouTube" or "YouTube" in found or not ev.get("youtube")): found.add(p)
    return [s for s in SOURCES if s in found]

def score(ev):
    vals = sorted(reach(ev).values(), reverse=True) + [0, 0, 0]
    s = vals[0] + 0.10 * vals[1] + 0.05 * vals[2]
    s += min(12, 3 * max(0, len(sources(ev)) - 1))
    s += 3 if ev.get("kym_editorial") else 0
    s += 5 if ev.get("x_news") else 0
    s += 5 if ev.get("kym_views", 0) >= 50000 else 0
    return round(s, 1)

def save_thumb(im, out):
    """Downscale to MAX_PX and save as a fresh JPEG: no EXIF, GPS, XMP, ICC or comment metadata."""
    from PIL import Image, ImageOps
    im.seek(0)
    im = ImageOps.exif_transpose(im)          # keep the visual orientation, then drop EXIF entirely
    im = im.convert("RGB"); im.thumbnail((MAX_PX, MAX_PX))
    clean = Image.new("RGB", im.size); clean.paste(im)
    clean.save(out, "JPEG", quality=80, optimize=True)

def needs_fix(path):
    from PIL import Image
    try:
        with Image.open(path) as im:
            meta = set(im.info) - {"jfif", "jfif_version", "jfif_unit", "jfif_density", "dpi", "progressive", "progression"}
            return max(im.size) > MAX_PX or bool(meta) or im.format != "JPEG"
    except Exception:
        return True

def normalize_images():
    """Enforce the size cap + metadata strip on every existing thumbnail (idempotent)."""
    from PIL import Image
    for f in sorted(IMG.glob("*.jpg")):
        if needs_fix(f):
            with Image.open(f) as im: save_thumb(im, f)
            print(f"  normalized {f.name}")

def accepted_url(url, field, cid):
    """URL safe to store in memes.json. Anything else is dropped before it is written."""
    if not isinstance(url, str) or not url:
        return ""
    return safe_url(url, context=f"{field} for {cid}")

def accepted_also(items, cid):
    """Drop also-links whose url is not on the allowlist. Other fields are unchanged."""
    kept = []
    for a in items or []:
        if not isinstance(a, dict):
            continue
        raw = a.get("url")
        if isinstance(raw, str) and raw:
            ok = accepted_url(raw, "also.url", cid)
            if not ok:
                continue
            if ok != raw:
                a = {**a, "url": ok}
        kept.append(a)
    return kept

def fetch_image(c, url=None):
    if url is None:
        url = c.get("image_url")
    if not isinstance(url, str) or not url or safe_url(url) != url:
        return None
    out = IMG / f"{c['id']}.jpg"
    if out.exists() and out.stat().st_size > 0: return f"images/{out.name}"
    try:
        raw = subprocess.run(["curl", "-sfL", "--max-time", "30", "-A", UA, url],
                             capture_output=True, check=True).stdout
        from PIL import Image
        save_thumb(Image.open(io.BytesIO(raw)), out)
        return f"images/{out.name}"
    except Exception as e:
        print(f"  ! image download failed for {c['id']} ({e}); showing a text card", file=sys.stderr)
        return None

def reddit_authors():
    try:
        r = json.loads((ROOT / "raw" / "reddit.json").read_text())
        return {p["url"]: p.get("author") for v in r.values() for p in v if p.get("url")}
    except Exception:
        return {}

def main():
    no_img = "--no-images" in sys.argv
    IMG.mkdir(exist_ok=True)
    cf = DATA / "candidates.json"
    doc = json.loads(cf.read_text())
    blocks = load_blocklist()
    kept, dropped = [], []
    for c in doc["candidates"]:
        b = blocked_by(c, blocks)
        if b:
            dropped.append(c["id"]); print(f"  BLOCKED (takedown) {c['id']}: {b.get('reason', '')}")
            (IMG / f"{c['id']}.jpg").unlink(missing_ok=True)
        else: kept.append(c)
    if dropped:                                   # takedowns never come back, even if research re-adds them
        doc["candidates"] = kept; cf.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    cands = []
    for c in kept:
        why = exclusion_reason(c)
        if why: print(f"  EXCLUDED {c['id']}: {why}")
        else: cands.append(c)
    authors = reddit_authors()
    for c in cands: c["score"] = score(c["ev"]); c["sources"] = sources(c["ev"])
    if not no_img: normalize_images()
    out = {"updated": datetime.datetime.now(ZoneInfo("America/Los_Angeles")).isoformat(timespec="minutes")}
    for p in PERIODS:
        pool = sorted([c for c in cands if p in c.get("periods", [])], key=lambda c: -c["score"])[:10]
        rows = []
        for i, c in enumerate(pool, 1):
            pol = c.get("image_policy", "local")
            raw_img = c.get("image_url")
            img_url = accepted_url(raw_img, "image_url", c["id"]) if isinstance(raw_img, str) else ""
            local = None if (no_img or pol != "local") else fetch_image(c, img_url)
            ext = img_url if pol == "hotlink" and img_url else None
            # image_policy none still skips third-party photos. A mapped post card fills in only when there is no photo.
            local = post_card_image(c, local, ext)
            rows.append({"rank": i, "id": c["id"], "title": c["title"], "image": local, "image_url": ext,
                         **({"image_kind": "post_card"} if local and local.startswith("images/post-cards/") else {}),
                         "card_text": c.get("card_text"), "source_url": accepted_url(c["source_url"], "source_url", c["id"]),
                         "source_name": c["source_name"],
                         "credit": default_credit(c, authors),
                         "also": accepted_also(c.get("also") or [], c["id"]),
                         "first_seen": c["first_seen"], "score": c["score"], "sources": c["sources"], "notes": c.get("notes", "")})
            for k in ("name", "explainer", "origin", "kym_url"):   # optional meme-page fields (see UPDATE.md "Meme pages")
                if not c.get(k):
                    continue
                if k == "kym_url":
                    ok = accepted_url(c[k], "kym_url", c["id"])
                    if ok:
                        rows[-1][k] = ok
                    continue
                rows[-1][k] = c[k]
        out[p] = rows
        print(p); [print(f"  {r['rank']:>2}. {r['score']:5.1f}  {r['title'][:70]}  [{r['source_name']}]") for r in rows]
    (DATA / "memes.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print("wrote data/memes.json")

if __name__ == "__main__":
    main()
