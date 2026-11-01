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
"""
import json, math, sys, pathlib, subprocess, io, datetime
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA, IMG = ROOT / "data", ROOT / "images"
PERIODS = ["daily", "weekly", "monthly"]
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

def fetch_image(c, big=False):
    url = c.get("image_url")
    if not url: return None
    out = IMG / f"{c['id']}.jpg"
    if out.exists() and out.stat().st_size > 0: return f"images/{out.name}"
    try:
        raw = subprocess.run(["curl", "-sfL", "--max-time", "30", "-A", UA, url],
                             capture_output=True, check=True).stdout
        from PIL import Image
        im = Image.open(io.BytesIO(raw)); im.seek(0)
        im = im.convert("RGB"); im.thumbnail((900, 900) if big else (480, 480))
        im.save(out, "JPEG", quality=82, optimize=True)
        return f"images/{out.name}"
    except Exception as e:
        print(f"  ! image download failed for {c['id']} ({e}); hotlinking", file=sys.stderr)
        return None

def main():
    no_img = "--no-images" in sys.argv
    IMG.mkdir(exist_ok=True)
    cands = json.loads((DATA / "candidates.json").read_text())["candidates"]
    for c in cands: c["score"] = score(c["ev"])
    out = {"updated": datetime.datetime.now(ZoneInfo("America/Los_Angeles")).isoformat(timespec="minutes")}
    for p in PERIODS:
        pool = sorted([c for c in cands if p in c.get("periods", [])], key=lambda c: -c["score"])[:10]
        rows = []
        for i, c in enumerate(pool, 1):
            local = None if no_img else fetch_image(c, big=(p == "daily" and i == 1))
            rows.append({"rank": i, "title": c["title"], "image": local, "image_url": c.get("image_url"),
                         "card_text": c.get("card_text"), "source_url": c["source_url"], "source_name": c["source_name"],
                         "also": c.get("also", []), "first_seen": c["first_seen"], "score": c["score"], "notes": c.get("notes", "")})
        out[p] = rows
        print(p); [print(f"  {r['rank']:>2}. {r['score']:5.1f}  {r['title'][:70]}  [{r['source_name']}]") for r in rows]
    (DATA / "memes.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print("wrote data/memes.json")

if __name__ == "__main__":
    main()
