#!/usr/bin/env python3
"""Fetch Reddit top-of-period RSS feeds for meme subs, honoring rate limits.
Reddit's .json endpoints are blocked for anonymous clients from many hosts; the
Atom/RSS feed (/r/<sub>/top/.rss?t=day|week|month) works but allows ~1 req per
10-20 s. Output: raw/<sub>_<period>.xml and raw/reddit.json (parsed).
Usage: python3 tools/fetch_reddit.py [--subs memes,dankmemes] [--force]
"""
import os, re, sys, time, json, urllib.request, urllib.error, xml.etree.ElementTree as ET
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "raw")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
NS = {"a": "http://www.w3.org/2005/Atom", "media": "http://search.yahoo.com/mrss/"}

def fetch(url, tries=8):
    for i in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
                if body.strip():
                    return body
        except urllib.error.HTTPError as e:
            reset = e.headers.get("x-ratelimit-reset")
            wait = (int(float(reset)) + 3) if reset else 30
            print(f"  {e.code} on {url}; waiting {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        time.sleep(20)
    return None

def parse(path):
    root = ET.parse(path).getroot()
    out = []
    for i, e in enumerate(root.findall("a:entry", NS), 1):
        c = e.find("a:content", NS).text or ""
        imgs = re.findall(r'href="(https://i\.redd\.it/[^"]+)"', c)
        th = e.find("media:thumbnail", NS)
        pub = e.find("a:published", NS)
        out.append({
            "feed_rank": i,
            "title": e.find("a:title", NS).text,
            "url": e.find("a:link", NS).get("href"),
            "published": pub.text if pub is not None else "",
            "image": imgs[0] if imgs else "",
            "thumb": th.get("url") if th is not None else "",
            "author": (e.find("a:author/a:name", NS).text if e.find("a:author/a:name", NS) is not None else ""),
        })
    return out

def main():
    subs = "memes,dankmemes"
    force = "--force" in sys.argv
    if "--subs" in sys.argv:
        subs = sys.argv[sys.argv.index("--subs") + 1]
    os.makedirs(RAW, exist_ok=True)
    result = {}
    for sub in subs.split(","):
        for t in ("day", "week", "month"):
            path = os.path.join(RAW, f"{sub}_{t}.xml")
            if force or not os.path.exists(path) or os.path.getsize(path) == 0:
                body = fetch(f"https://www.reddit.com/r/{sub}/top/.rss?t={t}&limit=25")
                if body:
                    open(path, "wb").write(body)
                    print(f"ok {sub} {t}", file=sys.stderr)
                time.sleep(15)
            try:
                result[f"{sub}_{t}"] = parse(path)
            except Exception as ex:
                print(f"parse fail {path}: {ex}", file=sys.stderr)
    json.dump(result, open(os.path.join(RAW, "reddit.json"), "w"), indent=1)
    print("wrote raw/reddit.json", {k: len(v) for k, v in result.items()})

if __name__ == "__main__":
    main()
