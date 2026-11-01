#!/usr/bin/env python3
"""Score candidates, pick Top 10 per period, download thumbnails, write data/memes.json.

Usage:  python3 tools/rank.py [--no-images]

Scoring rubric (virality evidence, documented in UPDATE.md):
  base  = 10*log10(peak_views)            # best single post/compilation views (X API or KYM-cited)
        or 10*log10(peak_likes*10)        # if only likes are known (likes x10 ~ views proxy)
        or Reddit feed-position proxy     # r/memes: 62-2*(rank-1); r/dankmemes: 60-2*(rank-1)
        (take the max if several apply)
  +5 per extra platform with confirmed spread (max +10)
  +5 documented on Know Your Meme        +3 picked in a KYM editorial / Meme-of-the-Month poll
  +5 X News trending story               +5 KYM entry page views >= 50,000

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

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA, IMG = ROOT / "data", ROOT / "images"
PERIODS = ["daily", "weekly", "monthly"]
MAX_PX = 400            # thumbnail cap (longest side), all positions incl. the top story
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

def score(ev):
    cands = []
    if ev.get("peak_views"): cands.append(10 * math.log10(ev["peak_views"]))
    if ev.get("peak_likes"): cands.append(10 * math.log10(ev["peak_likes"] * 10))
    r = ev.get("reddit")
    if r: cands.append((62 if r["sub"] == "memes" else 60) - 2 * (r["rank"] - 1))
    s = max(cands) if cands else 0
    s += min(10, 5 * max(0, len(ev.get("platforms", [])) - 1))
    s += 5 if ev.get("kym") else 0
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

def fetch_image(c):
    url = c.get("image_url")
    if not url: return None
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
    for c in cands: c["score"] = score(c["ev"])
    if not no_img: normalize_images()
    out = {"updated": datetime.datetime.now(ZoneInfo("America/Los_Angeles")).isoformat(timespec="minutes")}
    for p in PERIODS:
        pool = sorted([c for c in cands if p in c.get("periods", [])], key=lambda c: -c["score"])[:10]
        rows = []
        for i, c in enumerate(pool, 1):
            pol = c.get("image_policy", "local")
            local = None if (no_img or pol != "local") else fetch_image(c)
            ext = c.get("image_url") if pol == "hotlink" else None
            rows.append({"rank": i, "id": c["id"], "title": c["title"], "image": local, "image_url": ext,
                         "card_text": c.get("card_text"), "source_url": c["source_url"], "source_name": c["source_name"],
                         "credit": default_credit(c, authors),
                         "also": c.get("also") or [], "first_seen": c["first_seen"], "score": c["score"], "notes": c.get("notes", "")})
        out[p] = rows
        print(p); [print(f"  {r['rank']:>2}. {r['score']:5.1f}  {r['title'][:70]}  [{r['source_name']}]") for r in rows]
    (DATA / "memes.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print("wrote data/memes.json")

if __name__ == "__main__":
    main()
