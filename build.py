#!/usr/bin/env python3
"""Render index.html from data/memes.json (Drudge-style).  Usage: python3 build.py"""
import json, html, datetime, pathlib
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent
data = json.loads((ROOT / "data" / "memes.json").read_text())
e = lambda s: html.escape(s or "", quote=True)

def updated_label():
    try: dt = datetime.datetime.fromisoformat(data["updated"]).astimezone(ZoneInfo("America/Los_Angeles"))
    except Exception: dt = datetime.datetime.now(ZoneInfo("America/Los_Angeles"))
    return dt.strftime("%a %b %-d, %Y %-I:%M %p PT").upper()

def thumb(m, cls="thumb"):
    src = m.get("image") or m.get("image_url")
    if src:
        return f'<a href="{e(m["source_url"])}" target="_blank" rel="noopener"><img class="{cls}" src="{e(src)}" alt="{e(m["title"])}" loading="lazy"></a>'
    return f'<a class="card {cls}" href="{e(m["source_url"])}" target="_blank" rel="noopener">{e(m.get("card_text") or m["title"])}</a>'

def item(m):
    also = " ".join(f'<a class="src" href="{e(a["url"])}" target="_blank" rel="noopener">{e(a["name"])}</a>' for a in m.get("also", []))
    return f'''<li>
  {thumb(m)}
  <div class="hl"><span class="rk">{m["rank"]}.</span> <a href="{e(m["source_url"])}" target="_blank" rel="noopener">{e(m["title"])}</a></div>
  <div class="meta"><a class="src" href="{e(m["source_url"])}" target="_blank" rel="noopener">{e(m["source_name"])}</a> {also}<span class="fs">since {e(m["first_seen"])}</span></div>
</li>'''

def column(title, rows, skip_first=False):
    rows = rows[1:] if skip_first else rows
    return f'<section class="col"><h2>{title}</h2><ul>{"".join(item(m) for m in rows)}</ul></section>'

top = data["daily"][0]
page = f'''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>MEMESTAND.COM -- THE TOP MEMES, TODAY / THIS WEEK / THIS MONTH</title>
<meta name="description" content="MemeStand: the internet's top memes, ranked daily, weekly and monthly.">
<meta http-equiv="refresh" content="1800">
<style>
 body{{background:#fff;color:#000;font-family:"Courier New",Courier,monospace;margin:0 auto;max-width:1180px;padding:10px 14px 40px}}
 a{{color:#000;text-decoration:none}} a:hover{{text-decoration:underline}}
 .mast{{text-align:center;border-bottom:3px double #000;padding-bottom:8px}}
 .mast h1{{font-size:56px;letter-spacing:4px;margin:6px 0 0;font-weight:bold}}
 .mast .tag{{font-size:13px;letter-spacing:2px}}
 .upd{{text-align:center;font-size:12px;margin:6px 0 2px}}
 .top{{text-align:center;margin:18px auto 22px;max-width:900px}}
 .top img{{max-width:100%;max-height:520px;border:1px solid #000}}
 .top .card{{min-height:240px;font-size:28px}}
 .top .hl a{{color:#c00;font-size:40px;font-weight:bold;line-height:1.12;text-transform:uppercase}}
 .top .meta{{margin-top:6px}}
 .grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;border-top:3px double #000;padding-top:10px}}
 @media(max-width:860px){{.grid{{grid-template-columns:1fr}} .mast h1{{font-size:38px}} .top .hl a{{font-size:28px}}}}
 h2{{font-size:20px;text-align:center;text-decoration:underline;margin:6px 0 12px}}
 ul{{list-style:none;padding:0;margin:0}} li{{margin:0 0 18px;padding-bottom:14px;border-bottom:1px dotted #999}}
 .thumb{{display:block;width:100%;max-height:260px;object-fit:contain;background:#fff;border:1px solid #ccc;margin-bottom:6px}}
 .card{{display:flex;align-items:center;justify-content:center;text-align:center;min-height:120px;padding:14px;border:2px solid #000;font-weight:bold;font-size:17px;background:#fff;box-sizing:border-box}}
 .hl{{font-size:16px;font-weight:bold;line-height:1.25;text-transform:uppercase}} .rk{{color:#c00}}
 .meta{{font-size:11px;margin-top:4px;color:#444}} .src{{color:#00c;margin-right:8px}} .fs{{color:#777}}
 footer{{border-top:3px double #000;margin-top:20px;padding-top:10px;font-size:11px;text-align:center;color:#444}}
</style></head><body>
<header class="mast"><h1>MEMESTAND</h1><div class="tag">THE INTERNET'S TOP MEMES -- RANKED BY VIRALITY</div></header>
<div class="upd">UPDATED {updated_label()}</div>
<div class="top">
  {thumb(top, "topimg")}
  <div class="hl"><a href="{e(top["source_url"])}" target="_blank" rel="noopener">{e(top["title"])}</a></div>
  <div class="meta"><a class="src" href="{e(top["source_url"])}" target="_blank" rel="noopener">{e(top["source_name"])}</a>{"".join(f' <a class="src" href="{e(a["url"])}" target="_blank" rel="noopener">{e(a["name"])}</a>' for a in top.get("also", []))}</div>
</div>
<main class="grid">
  {column("TOP 10 MEMES TODAY", data["daily"])}
  {column("TOP 10 THIS WEEK", data["weekly"])}
  {column("TOP 10 THIS MONTH", data["monthly"])}
</main>
<footer>RANKED BY CROSS-PLATFORM VIRALITY: X ENGAGEMENT, KNOW YOUR MEME, REDDIT TOP FEEDS, X TRENDING STORIES.<br>
ALL MEMES BELONG TO THEIR CREATORS; THUMBNAILS LINK TO THE ORIGINAL SOURCE. TAKEDOWN REQUESTS HONORED. &copy; MEMESTAND.COM</footer>
</body></html>'''
(ROOT / "index.html").write_text(page)
print("wrote", ROOT / "index.html")
