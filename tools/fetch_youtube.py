#!/usr/bin/env python3
"""Pull public YouTube search results for meme queries (no API key, no login) into raw/youtube.json.

Usage:  python3 tools/fetch_youtube.py [--query "extra phrase" ...] [--video VIDEO_ID ...]

- Default queries: "meme", "memes", "meme trend", "viral meme", "#shorts meme", filtered to uploads from
  the last 24h ("today") and the last 7 days ("week"), sorted by view count.
- Each extra --query (e.g. a candidate's key phrase) is searched with the "this week, by views" filter.
- --video ID re-checks one video's watch page (title, channel, exact view count, upload date).
Parses the page's embedded ytInitialData JSON. View counts are YouTube's public display counts.
"""
import json, re, sys, pathlib, subprocess, urllib.parse, time, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
# sp filters: upload date + sort by view count (protobuf-encoded, as YouTube's own filter links use)
SP = {"today": "CAMSBAgCEAE", "week": "CAMSBAgDEAE", "month": "CAMSBAgEEAE"}   # sort=views, upload date today/week/month, type=video
DEFAULT = ["meme", "memes", "meme trend", "viral meme", "#shorts meme"]

def get(url):
    return subprocess.run(["curl", "-sL", "--max-time", "30", "-A", UA, "-H", "Accept-Language: en-US,en;q=0.9",
                           "-b", "CONSENT=YES+1", url], capture_output=True, text=True).stdout

def initial_data(page, var="ytInitialData"):
    m = re.search(r"(?:var |window\[\")" + var + r"(?:\"\])?\s*=\s*", page)
    if not m: return {}
    try: return json.JSONDecoder().raw_decode(page, m.end())[0]
    except ValueError: return {}

def views_num(s):
    if not s: return None
    s = s.replace(",", "").lower()
    m = re.search(r"([\d.]+)\s*([kmb]?)", s)
    if not m: return None
    return int(float(m.group(1)) * {"": 1, "k": 1e3, "m": 1e6, "b": 1e9}[m.group(2)])

def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values(): yield from walk(v)
    elif isinstance(o, list):
        for v in o: yield from walk(v)

def txt(x):
    if not x: return ""
    if "simpleText" in x: return x["simpleText"]
    return "".join(r.get("text", "") for r in x.get("runs", []))

def parse_results(data):
    out = []
    for d in walk(data):
        if "videoRenderer" in d:
            v = d["videoRenderer"]
            vt = txt(v.get("viewCountText"))
            out.append({"type": "video", "id": v["videoId"], "url": f"https://www.youtube.com/watch?v={v['videoId']}",
                        "title": txt(v.get("title")), "channel": txt(v.get("ownerText")),
                        "views_text": vt, "views": views_num(vt), "published": txt(v.get("publishedTimeText")),
                        "length": txt(v.get("lengthText")),
                        "thumb": f"https://i.ytimg.com/vi/{v['videoId']}/hqdefault.jpg"})
        elif "shortsLockupViewModel" in d:
            s = d["shortsLockupViewModel"]
            vid = (s.get("onTap", {}).get("innertubeCommand", {}).get("reelWatchEndpoint", {}) or {}).get("videoId")
            ov = s.get("overlayMetadata", {})
            vt = (ov.get("secondaryText") or {}).get("content", "")
            if vid:
                out.append({"type": "short", "id": vid, "url": f"https://www.youtube.com/shorts/{vid}",
                            "title": (ov.get("primaryText") or {}).get("content", ""), "channel": "",
                            "views_text": vt, "views": views_num(vt), "published": "",
                            "thumb": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"})
    seen, uniq = set(), []
    for r in out:
        if r["id"] not in seen: seen.add(r["id"]); uniq.append(r)
    return uniq

def search(q, period):
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(q) + "&sp=" + SP[period]
    return parse_results(initial_data(get(url)))

def video(vid):
    page = get(f"https://www.youtube.com/watch?v={vid}")
    pr = initial_data(page, "ytInitialPlayerResponse")
    vd = pr.get("videoDetails", {}); mf = pr.get("microformat", {}).get("playerMicroformatRenderer", {})
    return {"id": vid, "url": f"https://www.youtube.com/watch?v={vid}", "title": vd.get("title"),
            "channel": vd.get("author"), "views": int(vd["viewCount"]) if vd.get("viewCount") else None,
            "published": mf.get("publishDate") or mf.get("uploadDate"), "playable": pr.get("playabilityStatus", {}).get("status")}

def main():
    args = sys.argv[1:]
    extra = [args[i + 1] for i, a in enumerate(args) if a == "--query"]
    vids = [args[i + 1] for i, a in enumerate(args) if a == "--video"]
    res = {"fetched": datetime.datetime.now().astimezone().isoformat(timespec="minutes"), "searches": {}, "videos": {}}
    if not extra and not vids:
        for q in DEFAULT:
            for p in ("today", "week"):
                res["searches"][f"{q} | {p}"] = search(q, p); time.sleep(1)
    for q in extra:
        res["searches"][f"{q} | week"] = search(q, "week"); time.sleep(1)
    for v in vids: res["videos"][v] = video(v)
    raw = ROOT / "raw"; raw.mkdir(exist_ok=True)
    name = "youtube.json" if not extra and not vids else "youtube_lookup.json"
    (raw / name).write_text(json.dumps(res, indent=1, ensure_ascii=False))
    for k, rows in res["searches"].items():
        print(f"== {k}: {len(rows)} results")
        for r in sorted(rows, key=lambda r: -(r["views"] or 0))[:12]:
            print(f"  {r['views'] or 0:>11,}  {r['type']:5} {r['url']}  {r['title'][:70]}  ({r['channel']}, {r['published']})")
    for v in res["videos"].values(): print(json.dumps(v, ensure_ascii=False))
    print(f"wrote raw/{name}")

if __name__ == "__main__":
    main()
