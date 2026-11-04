#!/usr/bin/env python3
"""Read public counts from TikTok and Instagram post pages (no API key, no login) into raw/social.json.

Usage:  python3 tools/fetch_social.py URL [URL ...]
        python3 tools/fetch_social.py --kym SLUG [--kym SLUG ...]   # every TikTok/Instagram/YouTube post a KYM entry embeds

- TikTok video/photo pages: the server-rendered __UNIVERSAL_DATA_FOR_REHYDRATION__ JSON has itemStruct.stats
  (playCount, diggCount = likes, shareCount, commentCount) and createTime. Works anonymously with a browser UA.
- Instagram reel/post pages: anonymous requests usually get only og:description ("N likes, M comments - user on DATE").
  Instagram doesn't expose play counts publicly to logged-out visitors, so likes are the signal.
- YouTube: see tools/fetch_youtube.py (search + watch-page view counts).
Prints one line per URL; anything that can't be read is reported, never guessed.
"""
import json, re, sys, pathlib, subprocess, html, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

def get(url, ua=UA):
    r = subprocess.run(["curl", "-sL", "--max-time", "30", "-A", ua, "-H", "Accept-Language: en-US,en;q=0.9", url,
                        "-w", "\n__HTTP__%{http_code}"], capture_output=True, text=True)
    body, _, code = r.stdout.rpartition("\n__HTTP__")
    return body, code

def num(s):
    s = s.replace(",", "").strip().upper()
    m = re.match(r"([\d.]+)\s*([KMB]?)", s)
    return int(float(m.group(1)) * {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(2)]) if m else None

def tiktok(url):
    page, code = get(url)
    m = re.search(r'id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', page, re.S)
    out = {"platform": "TikTok", "url": url, "http": code}
    if not m: return {**out, "error": "no rehydration data"}
    d = json.loads(m.group(1)).get("__DEFAULT_SCOPE__", {})
    item = (d.get("webapp.video-detail") or d.get("webapp.reflow.video.detail") or {}).get("itemInfo", {}).get("itemStruct")
    if not item: return {**out, "error": "no itemStruct (removed, private or blocked)", "status": (d.get("webapp.video-detail") or {}).get("statusCode")}
    st = item.get("statsV2") or item.get("stats") or {}
    return {**out, "author": "@" + item.get("author", {}).get("uniqueId", ""), "desc": item.get("desc", "")[:140],
            "views": int(st.get("playCount", 0) or 0), "likes": int(st.get("diggCount", 0) or 0),
            "shares": int(st.get("shareCount", 0) or 0), "comments": int(st.get("commentCount", 0) or 0),
            "created": datetime.datetime.fromtimestamp(int(item.get("createTime", 0)), datetime.timezone.utc).date().isoformat(),
            "cover": (item.get("video") or {}).get("cover") or (item.get("video") or {}).get("originCover")}

def instagram(url):
    url = re.sub(r"instagram\.com/[^/]+/(reel|p)/", r"instagram.com/\1/", url.split("?")[0])
    page, code = get(url, "facebookexternalhit/1.1")
    if "og:description" not in page: page, code = get(url)
    out = {"platform": "Instagram", "url": url, "http": code}
    m = re.search(r'property="og:description" content="([^"]*)"', page) or re.search(r'name="description" content="([^"]*)"', page)
    if not m: return {**out, "error": "no og:description (login wall)"}
    desc = html.unescape(m.group(1))
    lk = re.search(r"([\d.,]+[KMB]?) likes?", desc, re.I); cm = re.search(r"([\d.,]+[KMB]?) comments?", desc, re.I)
    who = re.search(r"- ([\w.]+) on ([A-Z][a-z]+ \d{1,2}, \d{4})", desc)
    img = re.search(r'property="og:image" content="([^"]*)"', page)
    return {**out, "likes": num(lk.group(1)) if lk else None, "comments": num(cm.group(1)) if cm else None,
            "author": "@" + who.group(1) if who else None, "date": who.group(2) if who else None, "og": desc[:200],
            "image": html.unescape(img.group(1)) if img else None}

def youtube(url):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from fetch_youtube import video
    vid = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([\w-]{11})", url)
    return {"platform": "YouTube", **video(vid.group(1))} if vid else {"platform": "YouTube", "url": url, "error": "no video id"}

def kym_posts(slug):
    page, _ = get(f"https://knowyourmeme.com/memes/{slug}")
    urls = set(re.findall(r'https?://(?:www\.)?tiktok\.com/@[\w.]+/(?:video|photo)/\d+', page))
    urls |= {re.sub(r"instagram\.com/[\w.]+/(reel|p)/", r"instagram.com/\1/", u.split("?")[0]).rstrip("/") + "/"
             for u in re.findall(r'https?://(?:www\.)?instagram\.com/(?:[\w.]+/)?(?:reel|p)/[\w-]+/?', page)}
    urls |= set(re.findall(r'https?://(?:www\.)?youtube\.com/(?:watch\?v=|shorts/|embed/)[\w-]{11}', page))
    return sorted(urls)

def read(url):
    if "tiktok.com" in url: return tiktok(url)
    if "instagram.com" in url: return instagram(url)
    if "youtube.com" in url or "youtu.be" in url: return youtube(url)
    return {"url": url, "error": "unsupported"}

def main():
    args, urls = sys.argv[1:], []
    for i, a in enumerate(args):
        if a == "--kym": urls += kym_posts(args[i + 1])
        elif not (i and args[i - 1] == "--kym"): urls.append(a)
    raw = ROOT / "raw"; raw.mkdir(exist_ok=True)
    f = raw / "social.json"
    store = json.loads(f.read_text()) if f.exists() else {}
    for u in dict.fromkeys(urls):
        try: r = read(u)
        except Exception as e: r = {"url": u, "error": f"{type(e).__name__}: {e}"}
        r["fetched"] = datetime.datetime.now().astimezone().isoformat(timespec="minutes"); store[r.get("url", u)] = r
        print(json.dumps({k: v for k, v in r.items() if k not in ("cover", "image", "fetched")}, ensure_ascii=False), flush=True)
        f.write_text(json.dumps(store, indent=1, ensure_ascii=False))
    f.write_text(json.dumps(store, indent=1, ensure_ascii=False))

if __name__ == "__main__":
    main()
