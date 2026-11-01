#!/usr/bin/env python3
"""Render the whole static site from data/memes.json (Drudge-style).   Usage: python3 build.py

Writes (all generated, don't hand-edit):
  index.html                          homepage: #1 story + three top-10 columns
  top-memes-today/index.html          single-list pages with evidence notes
  trending-memes-this-week/index.html
  best-memes-this-month/index.html
  archive/YYYY-MM-DD.html             one "Daily Meme Report" per day (rendered from data/archive/*.json)
  archive/index.html                  archive index
  about.html                          what MemeStand is + ranking method
  feed.xml                            Atom feed, one entry per daily report
  sitemap.xml, robots.txt, llms.txt   crawler / AI-assistant discovery

Each run snapshots data/memes.json to data/archive/<PT date>.json (overwriting only today's
snapshot), and never deletes older snapshots or archive pages, so past days survive rebuilds.
The build is deterministic: re-running with the same data produces identical files.
"""
import json, html, datetime, pathlib, re, shutil
from zoneinfo import ZoneInfo

SITE = "https://memestand.com"
NAME = "MemeStand"
PT = ZoneInfo("America/Los_Angeles")
ROOT = pathlib.Path(__file__).resolve().parent
ARCH_DATA, ARCH = ROOT / "data" / "archive", ROOT / "archive"
data = json.loads((ROOT / "data" / "memes.json").read_text())
e = lambda s: html.escape(str(s or ""), quote=True)

def parse_dt(d):
    try: return datetime.datetime.fromisoformat(d["updated"]).astimezone(PT)
    except Exception: return datetime.datetime.now(PT).replace(second=0, microsecond=0)

NOW = parse_dt(data)
TODAY = NOW.date().isoformat()
ISO = NOW.isoformat(timespec="seconds")
fmt_long = lambda d: d.strftime("%B %-d, %Y")          # November 1, 2026
fmt_short = lambda d: d.strftime("%b %-d, %Y")         # Nov 1, 2026

ACRONYMS = {"PC", "PC'S", "RAM", "AI", "NNN", "GPU", "TV", "US", "UK", "NBA", "NFL", "KYM", "CEO", "DIMMS", "DIMM", "GTA", "NPC", "POV", "OK", "LOL", "X", "H3'S", "H3", "USA", "NYC", "LA", "MLB", "UFC", "WWE"}
SPECIAL = {"DIMMS": "DIMMs", "MEMES": "Memes", "IPHONE": "iPhone", "YOUTUBE": "YouTube", "TIKTOK": "TikTok", "CHATGPT": "ChatGPT", "MRBEAST": "MrBeast"}
SMALL = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to", "vs", "with", "is"}
def tc(s):
    """Headline in ALL CAPS -> readable Title Case for titles/descriptions/alt text."""
    out = []
    for i, w in enumerate((s or "").split()):
        core = re.sub(r"^[^\w]+|[^\w']+$", "", w)
        if core.upper() in SPECIAL: out.append(w.replace(core, SPECIAL[core.upper()])); continue
        if core.upper().endswith("'S") and core.upper()[:-2] in ACRONYMS: out.append(w[:-1] + "s"); continue
        if core.upper() in ACRONYMS or re.search(r"\d", core): out.append(w); continue
        lw = w.lower()
        if i and core.lower() in SMALL: out.append(lw); continue
        out.append(re.sub(r"[a-z]", lambda m: m.group().upper(), lw, count=1))
    return " ".join(out)

def img_src(m):  return m.get("image") or m.get("image_url")
def abs_img(m):
    s = img_src(m)
    if not s: return None
    return s if s.startswith("http") else f"{SITE}/{s}"

PERIODS = {
    "daily":   {"h2": "TOP 10 MEMES TODAY",      "slug": "top-memes-today",          "word": "today"},
    "weekly":  {"h2": "TOP 10 MEMES THIS WEEK",  "slug": "trending-memes-this-week", "word": "this week"},
    "monthly": {"h2": "TOP 10 MEMES THIS MONTH", "slug": "best-memes-this-month",    "word": "this month"},
}

CSS = """
 body{background:#fff;color:#000;font-family:"Courier New",Courier,monospace;margin:0 auto;max-width:1180px;padding:10px 14px 40px}
 a{color:#000;text-decoration:none} a:hover{text-decoration:underline}
 .mast{text-align:center;border-bottom:3px double #000;padding-bottom:8px}
 .mast h1{margin:6px 0 0;font-weight:bold;font-size:inherit}
 .mast .logo{display:block;font-size:56px;letter-spacing:4px} .mast .logo a{color:#000}
 .mast .tag{display:block;font-size:13px;letter-spacing:2px;font-weight:normal}
 .intro{text-align:center;font-size:12px;margin:6px auto 0;max-width:820px;color:#333}
 .upd{text-align:center;font-size:12px;margin:6px 0 2px}
 .top{text-align:center;margin:18px auto 22px;max-width:900px}
 .top img{max-width:100%;max-height:520px;border:1px solid #000}
 .top .card{min-height:240px;font-size:28px}
 .top h2{margin:6px 0 0;text-decoration:none}
 .top .hl a{color:#c00;font-size:40px;font-weight:bold;line-height:1.12;text-transform:uppercase}
 .top .meta{margin-top:6px}
 .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;border-top:3px double #000;padding-top:10px}
 .one{max-width:640px;margin:0 auto;border-top:3px double #000;padding-top:10px}
 @media(max-width:860px){.grid{grid-template-columns:1fr} .mast .logo{font-size:38px} .top .hl a{font-size:28px}}
 h2{font-size:20px;text-align:center;text-decoration:underline;margin:6px 0 12px} h2 a{color:#000}
 h3{margin:0;font-size:inherit}
 ul{list-style:none;padding:0;margin:0} li{margin:0 0 18px;padding-bottom:14px;border-bottom:1px dotted #999}
 .thumb{display:block;width:100%;max-height:260px;object-fit:contain;background:#fff;border:1px solid #ccc;margin-bottom:6px}
 .one .thumb{max-height:420px}
 .card{display:flex;align-items:center;justify-content:center;text-align:center;min-height:120px;padding:14px;border:2px solid #000;font-weight:bold;font-size:17px;background:#fff;box-sizing:border-box}
 .hl{font-size:16px;font-weight:bold;line-height:1.25;text-transform:uppercase} .rk{color:#c00}
 .meta{font-size:11px;margin-top:4px;color:#444} .src{color:#00c;margin-right:8px} .fs{color:#777}
 .why{font-size:12px;margin-top:4px;color:#222}
 .more{text-align:center;font-size:12px;margin:4px 0 0} .more a{color:#00c}
 .pager{text-align:center;font-size:13px;margin:14px 0} .pager a{color:#00c;margin:0 10px}
 .prose{max-width:760px;margin:16px auto;font-size:14px;line-height:1.5} .prose a{color:#00c} .prose td,.prose th{border:1px solid #999;padding:3px 6px;font-size:12px} .prose table{border-collapse:collapse}
 nav.foot{margin-bottom:6px;font-size:12px} nav.foot a{color:#00c;margin:0 6px}
 footer{border-top:3px double #000;margin-top:20px;padding-top:10px;font-size:11px;text-align:center;color:#444}
"""

# ---------------------------------------------------------------- page chrome
def head(*, title, desc, path, base, og_img=None, og_alt=None, og_type="website", ld=(), modified=None):
    url = f"{SITE}/{path}"
    og_img = og_img or f"{SITE}/og-default.png"
    og_alt = og_alt or "MemeStand: top 10 memes today, this week and this month"
    lds = "\n".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")}</script>' for x in ld)
    mod = f'\n<meta property="article:modified_time" content="{e(modified)}">' if modified and og_type == "article" else ""
    return f'''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1">
<link rel="canonical" href="{e(url)}">
<link rel="icon" href="{base}favicon.ico" sizes="any"><link rel="icon" href="{base}favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="{base}apple-touch-icon.png">
<link rel="alternate" type="application/atom+xml" title="MemeStand Daily Meme Report" href="{SITE}/feed.xml">
<meta property="og:site_name" content="{NAME}">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(url)}">
<meta property="og:image" content="{e(og_img)}">
<meta property="og:image:alt" content="{e(og_alt)}">
<meta property="og:locale" content="en_US">{mod}
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(desc)}">
<meta name="twitter:image" content="{e(og_img)}">
<meta name="twitter:image:alt" content="{e(og_alt)}">
{lds}
<style>{CSS}</style></head><body>'''

def mast(base, tag, h1=True):
    inner = f'<span class="logo"><a href="{base}index.html">MEMESTAND</a></span><span class="tag">{tag}</span>'
    return f'<header class="mast">{"<h1>" + inner + "</h1>" if h1 else "<div>" + inner + "</div>"}</header>'

INTRO = ("MemeStand is a daily meme report: the internet's top 10 memes today, this week and this month, "
         "ranked by cross-platform virality on X, Reddit and Know Your Meme. Updated every morning.")

def footer(base):
    links = [("index.html", "Home"), ("top-memes-today/", "Top Memes Today"), ("trending-memes-this-week/", "Trending This Week"),
             ("best-memes-this-month/", "Best of the Month"), ("archive/", "Daily Meme Report Archive"),
             ("feed.xml", "RSS/Atom Feed"), ("about.html", "About &amp; Method"), ("llms.txt", "llms.txt")]
    nav = " | ".join(f'<a href="{base}{u}">{t}</a>' for u, t in links)
    return f'''<footer><nav class="foot">{nav}</nav>
RANKED BY CROSS-PLATFORM VIRALITY: X ENGAGEMENT, KNOW YOUR MEME, REDDIT TOP FEEDS, X TRENDING STORIES.<br>
ALL MEMES BELONG TO THEIR CREATORS; THUMBNAILS LINK TO THE ORIGINAL SOURCE. TAKEDOWN REQUESTS HONORED. &copy; MEMESTAND.COM</footer>
</body></html>
'''

# ---------------------------------------------------------------- items
def alt(m, label):
    a = f"{tc(m['title'])} meme"
    return f"{a} - #{m['rank']} {label} on MemeStand" if label else a

def thumb(m, base, label, cls="thumb", eager=False):
    src = img_src(m)
    if src:
        src = src if src.startswith("http") else base + src
        load = 'fetchpriority="high"' if eager else 'loading="lazy"'
        return f'<a href="{e(m["source_url"])}" target="_blank" rel="noopener"><img class="{cls}" src="{e(src)}" alt="{e(alt(m, label))}" {load}></a>'
    return f'<a class="card {cls}" href="{e(m["source_url"])}" target="_blank" rel="noopener">{e(m.get("card_text") or m["title"])}</a>'

def sources(m, lead=" "):
    also = " ".join(f'<a class="src" href="{e(a["url"])}" target="_blank" rel="noopener">{e(a["name"])}</a>' for a in m.get("also", []))
    return f'<a class="src" href="{e(m["source_url"])}" target="_blank" rel="noopener">{e(m["source_name"])}</a>{lead}{also}'

def item(m, base, label, notes=False):
    why = f'\n  <div class="why">Why it ranks: {e(m["notes"])}</div>' if notes and m.get("notes") else ""
    return f'''<li>
  {thumb(m, base, label)}
  <h3 class="hl"><span class="rk">{m["rank"]}.</span> <a href="{e(m["source_url"])}" target="_blank" rel="noopener">{e(m["title"])}</a></h3>
  <div class="meta">{sources(m)}<span class="fs">since {e(m["first_seen"])}</span></div>{why}
</li>'''

def column(d, p, base, link=True, notes=False):
    info = PERIODS[p]
    h = f'<a href="{base}{info["slug"]}/">{info["h2"]}</a>' if link else info["h2"]
    return f'<section class="col" id="{p}"><h2>{h}</h2><ul>{"".join(item(m, base, info["word"], notes) for m in d[p])}</ul></section>'

def top_story(d, base, kicker="TODAY'S #1 MEME"):
    t = d["daily"][0]
    return f'''<div class="top">
  {thumb(t, base, "today", "topimg", eager=True)}
  <h2 class="hl"><span class="rk" style="font-size:13px;display:block;letter-spacing:2px">{kicker}</span><a href="{e(t["source_url"])}" target="_blank" rel="noopener">{e(t["title"])}</a></h2>
  <div class="meta">{sources(t, "")}</div>
</div>'''

def og_for(d):
    t = d["daily"][0]
    img = abs_img(t) if t.get("image") else None    # only our own local thumbnail; else the default card
    return img, (alt(t, "today") if img else None)

# ---------------------------------------------------------------- structured data
ORG = {"@type": "Organization", "@id": f"{SITE}/#org", "name": NAME, "url": f"{SITE}/",
       "logo": {"@type": "ImageObject", "url": f"{SITE}/apple-touch-icon.png", "width": 180, "height": 180}}
WEBSITE = {"@type": "WebSite", "@id": f"{SITE}/#website", "name": NAME, "alternateName": "MemeStand.com", "url": f"{SITE}/",
           "description": INTRO, "inLanguage": "en", "publisher": {"@id": f"{SITE}/#org"}}

def itemlist(d, p, page_url, date_label):
    info = PERIODS[p]
    els = []
    for m in d[p]:
        li = {"@type": "ListItem", "position": m["rank"], "name": tc(m["title"]), "url": m["source_url"]}
        img = abs_img(m)
        if img: li["image"] = img
        els.append(li)
    return {"@type": "ItemList", "@id": f"{page_url}#{p}", "name": f"Top 10 Memes {info['word'].title()} ({date_label})",
            "itemListOrder": "https://schema.org/ItemListOrderDescending", "numberOfItems": len(els), "itemListElement": els}

def graph(*nodes): return {"@context": "https://schema.org", "@graph": list(nodes)}

def webpage(url, name, desc, modified, published=None, kind="CollectionPage", crumbs=None, about_lists=()):
    n = {"@type": kind, "@id": url, "url": url, "name": name, "description": desc, "inLanguage": "en",
         "isPartOf": {"@id": f"{SITE}/#website"}, "publisher": {"@id": f"{SITE}/#org"}, "dateModified": modified}
    if published: n["datePublished"] = published
    if about_lists: n["mainEntity"] = [{"@id": x} for x in about_lists]
    if crumbs:
        n["breadcrumb"] = {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i, "name": nm, "item": u} for i, (nm, u) in enumerate(crumbs, 1)]}
    return n

# ---------------------------------------------------------------- writers
written = []
def write(rel, text):
    p = ROOT / rel; p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists() or p.read_text() != text: p.write_text(text)
    written.append(rel)

def build_home():
    d, url = data, f"{SITE}/"
    t1 = tc(d["daily"][0]["title"])
    title = "MemeStand — Top 10 Memes Today, This Week & This Month | Daily Meme Report"
    desc = (f"MemeStand's daily meme report: the internet's top 10 trending memes today, this week and this month, "
            f"ranked by virality. Today's #1 ({fmt_short(NOW)}): \"{t1}\".")
    og, og_alt = og_for(d)
    lists = [itemlist(d, p, url, fmt_short(NOW)) for p in PERIODS]
    ld = graph(ORG, WEBSITE, webpage(url, title, desc, ISO, about_lists=[x["@id"] for x in lists]), *lists)
    page = head(title=title, desc=desc, path="", base="", og_img=og, og_alt=og_alt, ld=[ld]) + f'''
{mast("", "THE TOP MEMES TODAY, THIS WEEK &amp; THIS MONTH -- RANKED BY VIRALITY")}
<p class="intro">{INTRO}</p>
<div class="upd">UPDATED <time datetime="{ISO}">{NOW.strftime("%a %b %-d, %Y %-I:%M %p PT").upper()}</time></div>
{top_story(d, "")}
<main class="grid">
  {column(d, "daily", "")}
  {column(d, "weekly", "")}
  {column(d, "monthly", "")}
</main>
<p class="more"><a href="archive/{TODAY}.html">Today's daily meme report ({fmt_long(NOW)})</a> | <a href="archive/">Past daily meme reports</a></p>
''' + footer("")
    write("index.html", page)

def build_period(p):
    d, info, base = data, PERIODS[p], "../"
    url = f"{SITE}/{info['slug']}/"
    t = tc(d[p][0]["title"])
    if p == "daily":
        title = f"Top 10 Memes Today ({fmt_short(NOW)}) — Trending Memes Right Now | MemeStand"
        h1 = f"TOP 10 MEMES TODAY -- {fmt_long(NOW).upper()}"
        desc = f"Today's top memes, {fmt_long(NOW)}: #1 is \"{t}\". The 10 most viral memes of the last 24-36 hours, ranked with the evidence from X, Reddit and Know Your Meme."
    elif p == "weekly":
        start = NOW.date() - datetime.timedelta(days=6)
        title = f"Trending Memes This Week — Top 10 ({start.strftime('%b %-d')}–{fmt_short(NOW)}) | MemeStand"
        h1 = f"TRENDING MEMES THIS WEEK -- TOP 10 ({start.strftime('%b %-d').upper()} - {fmt_short(NOW).upper()})"
        desc = f"The top 10 trending memes this week ({start.strftime('%b %-d')}–{fmt_short(NOW)}): #1 is \"{t}\". Ranked by cross-platform virality, updated daily."
    else:
        title = f"Best Memes of the Month — Top 10, Last 30 Days ({NOW.strftime('%B %Y')}) | MemeStand"
        h1 = f"BEST MEMES OF THE MONTH -- TOP 10, LAST 30 DAYS"
        desc = f"The best memes of the month (last 30 days, updated {fmt_short(NOW)}): #1 is \"{t}\". The 10 biggest memes ranked by reach and cross-platform spread."
    lst = itemlist(d, p, url, fmt_short(NOW))
    crumbs = [("MemeStand", f"{SITE}/"), (info["h2"].title(), url)]
    m1 = d[p][0]
    og = abs_img(m1) if m1.get("image") else None
    ld = graph(ORG, WEBSITE, webpage(url, title, desc, ISO, crumbs=crumbs, about_lists=[lst["@id"]]), lst)
    others = " | ".join(f'<a href="../{v["slug"]}/">{v["h2"].title()}</a>' for k, v in PERIODS.items() if k != p)
    page = head(title=title, desc=desc, path=f"{info['slug']}/", base=base, og_img=og, og_alt=alt(m1, info["word"]) if og else None, ld=[ld]) + f'''
{mast(base, h1)}
<p class="intro">{INTRO}</p>
<div class="upd">UPDATED <time datetime="{ISO}">{NOW.strftime("%a %b %-d, %Y %-I:%M %p PT").upper()}</time></div>
<main class="one">{column(d, p, base, link=False, notes=True)}</main>
<p class="pager">{others} | <a href="../archive/">Daily Meme Report Archive</a></p>
''' + footer(base)
    write(f"{info['slug']}/index.html", page)

def snapshots():
    ARCH_DATA.mkdir(parents=True, exist_ok=True)
    snap = ARCH_DATA / f"{TODAY}.json"
    txt = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if not snap.exists() or snap.read_text() != txt: snap.write_text(txt)
    out = []
    for f in sorted(ARCH_DATA.glob("????-??-??.json")):
        try: out.append((f.stem, json.loads(f.read_text())))
        except Exception as ex: print("  ! skipping bad snapshot", f, ex)
    return out   # oldest -> newest

def build_archive_day(day, d, prev, nxt):
    dt, base = parse_dt(d), "../"
    dd = datetime.date.fromisoformat(day)
    url = f"{SITE}/archive/{day}.html"
    t = tc(d["daily"][0]["title"])
    title = f"Daily Meme Report, {fmt_long(dd)} — Top Memes of the Day | MemeStand"
    desc = f"MemeStand's daily meme report for {fmt_long(dd)}: #1 meme of the day was \"{t}\". Plus the top 10 memes of the day, the week and the month."
    lists = [itemlist(d, p, url, fmt_short(dd)) for p in PERIODS]
    iso = dt.isoformat(timespec="seconds")
    crumbs = [("MemeStand", f"{SITE}/"), ("Archive", f"{SITE}/archive/"), (fmt_long(dd), url)]
    wp = webpage(url, title, desc, iso, published=iso, crumbs=crumbs, about_lists=[x["@id"] for x in lists])
    og, og_alt = og_for(d)
    pager = []
    if prev: pager.append(f'<a href="{prev}.html">&larr; {fmt_short(datetime.date.fromisoformat(prev))}</a>')
    pager.append('<a href="index.html">All reports</a>')
    if nxt: pager.append(f'<a href="{nxt}.html">{fmt_short(datetime.date.fromisoformat(nxt))} &rarr;</a>')
    else: pager.append('<a href="../index.html">Live rankings &rarr;</a>')
    page = head(title=title, desc=desc, path=f"archive/{day}.html", base=base, og_img=og, og_alt=og_alt,
                og_type="article", ld=[graph(ORG, WEBSITE, wp, *lists)], modified=iso) + f'''
{mast(base, f"DAILY MEME REPORT -- {fmt_long(dd).upper()}")}
<p class="intro">The internet's top memes as ranked by MemeStand on {fmt_long(dd)}. Rankings below are frozen as of <time datetime="{iso}">{dt.strftime("%-I:%M %p PT")}</time> that day; see the homepage for live rankings.</p>
<p class="pager">{" ".join(pager)}</p>
{top_story(d, base, kicker=f"#1 MEME OF {fmt_short(dd).upper()}")}
<main class="grid">
  {column(d, "daily", base, link=False)}
  {column(d, "weekly", base, link=False)}
  {column(d, "monthly", base, link=False)}
</main>
<p class="pager">{" ".join(pager)}</p>
''' + footer(base)
    write(f"archive/{day}.html", page)

def build_archive_index(snaps):
    base, url = "../", f"{SITE}/archive/"
    title = "Daily Meme Report Archive — Top Memes by Date | MemeStand"
    desc = "Every MemeStand daily meme report: the #1 meme and top 10 memes of each day, week and month, by date."
    rows = "".join(f'<li><h3 class="hl"><a href="{day}.html">{fmt_long(datetime.date.fromisoformat(day)).upper()}</a></h3>'
                   f'<div class="meta">#1: {e(d["daily"][0]["title"])}</div></li>' for day, d in reversed(snaps))
    il = {"@type": "ItemList", "@id": f"{url}#reports", "name": "MemeStand daily meme reports", "numberOfItems": len(snaps),
          "itemListElement": [{"@type": "ListItem", "position": i, "url": f"{SITE}/archive/{day}.html",
                               "name": f"Daily Meme Report, {fmt_long(datetime.date.fromisoformat(day))}"}
                              for i, (day, _) in enumerate(reversed(snaps), 1)]}
    wp = webpage(url, title, desc, ISO, crumbs=[("MemeStand", f"{SITE}/"), ("Archive", url)], about_lists=[il["@id"]])
    page = head(title=title, desc=desc, path="archive/", base=base, ld=[graph(ORG, WEBSITE, wp, il)]) + f'''
{mast(base, "DAILY MEME REPORT ARCHIVE")}
<p class="intro">{e(desc)}</p>
<main class="one"><section class="col"><h2>PAST REPORTS</h2><ul>{rows}</ul></section></main>
''' + footer(base)
    write("archive/index.html", page)

def build_about():
    url = f"{SITE}/about.html"
    title = "About MemeStand — How We Rank the Internet's Top Memes"
    desc = "MemeStand ranks the top 10 memes today, this week and this month using a virality evidence score built from X, Reddit and Know Your Meme data."
    page = head(title=title, desc=desc, path="about.html", base="", ld=[graph(ORG, WEBSITE, webpage(url, title, desc, ISO, kind="AboutPage"))]) + f'''
{mast("", "ABOUT MEMESTAND -- HOW THE RANKINGS WORK")}
<main class="prose">
<h2>What is MemeStand?</h2>
<p>MemeStand (memestand.com) is a Drudge-style daily meme report. Every morning it publishes three ranked lists:
the <a href="top-memes-today/">top 10 memes today</a>, the <a href="trending-memes-this-week/">top 10 trending memes this week</a>
and the <a href="best-memes-this-month/">best memes of the month</a> (last 30 days). Each day's rankings are saved in the
<a href="archive/">daily meme report archive</a> and published in an <a href="feed.xml">Atom feed</a>.</p>
<h2>How are memes ranked?</h2>
<p>Each candidate meme gets a <b>virality evidence score</b>. Every meme listed links to a real, checked source post or entry.</p>
<table><tr><th>Signal</th><th>Points</th></tr>
<tr><td>Reach of the best post or compilation (X impressions, or views cited by Know Your Meme)</td><td>10 &times; log10(views); 1M = 60, 10M = 70</td></tr>
<tr><td>Only likes known</td><td>10 &times; log10(likes &times; 10)</td></tr>
<tr><td>Reddit top-feed position (r/memes, r/dankmemes)</td><td>#1 = 60-62, &minus;2 per rank</td></tr>
<tr><td>Each additional platform with confirmed spread</td><td>+5 (max +10)</td></tr>
<tr><td>Documented on Know Your Meme</td><td>+5</td></tr>
<tr><td>Picked in a KYM Weekly Roundup or Meme of the Month poll</td><td>+3</td></tr>
<tr><td>X trending news story about it</td><td>+5</td></tr>
<tr><td>Know Your Meme page views &ge; 50,000</td><td>+5</td></tr></table>
<p>Windows: <b>today</b> = took off in the last ~36 hours; <b>this week</b> = active in the last 7 days; <b>this month</b> = active in the last 30 days.</p>
<h2>Credits and takedowns</h2>
<p>All memes belong to their creators. MemeStand shows small thumbnails that link to the original source. Takedown requests are honored.</p>
</main>
''' + footer("")
    write("about.html", page)

def build_feed(snaps):
    entries = []
    for day, d in reversed(snaps[-60:]):
        dd, dt = datetime.date.fromisoformat(day), parse_dt(d)
        t = d["daily"][0]
        u = f"{SITE}/archive/{day}.html"
        lis = "".join(f"<li>{e(m['title'])} (<a href=\"{e(m['source_url'])}\">{e(m['source_name'])}</a>)</li>" for m in d["daily"])
        img = abs_img(t)
        imgh = f'<p><img src="{e(img)}" alt="{e(alt(t, "today"))}"></p>' if img else ""
        content = f"{imgh}<p>#1 meme of {fmt_long(dd)}: <a href=\"{e(t['source_url'])}\">{e(t['title'])}</a></p><p>Top 10 memes today:</p><ol>{lis}</ol>"
        entries.append(f'''<entry>
<title>{e(f"Top meme of {fmt_long(dd)}: {tc(t['title'])}")}</title>
<link href="{u}"/>
<id>{u}</id>
<published>{dt.isoformat(timespec="seconds")}</published>
<updated>{dt.isoformat(timespec="seconds")}</updated>
<summary>{e(f"MemeStand daily meme report for {fmt_long(dd)}. #1: {tc(t['title'])}.")}</summary>
<content type="html">{e(content)}</content>
</entry>''')
    feed = f'''<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>MemeStand Daily Meme Report</title>
<subtitle>The #1 meme of the day and the internet's top 10 memes, ranked daily.</subtitle>
<link href="{SITE}/feed.xml" rel="self" type="application/atom+xml"/>
<link href="{SITE}/" rel="alternate" type="text/html"/>
<id>{SITE}/</id>
<updated>{ISO}</updated>
<author><name>MemeStand</name><uri>{SITE}/</uri></author>
<icon>{SITE}/favicon.ico</icon>
{chr(10).join(entries)}
</feed>
'''
    write("feed.xml", feed)

def build_sitemap(snaps):
    urls = [("", ISO, "daily", "1.0")] + [(f"{v['slug']}/", ISO, "daily", "0.9") for v in PERIODS.values()] + \
           [("archive/", ISO, "daily", "0.6"), ("about.html", None, "monthly", "0.3")]
    urls += [(f"archive/{day}.html", parse_dt(d).isoformat(timespec="seconds"), "never", "0.5") for day, d in reversed(snaps)]
    body = "".join(f"<url><loc>{SITE}/{u}</loc>{f'<lastmod>{lm}</lastmod>' if lm else ''}<changefreq>{cf}</changefreq><priority>{pr}</priority></url>\n"
                   for u, lm, cf, pr in urls)
    write("sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}</urlset>\n')

BOTS = ["Googlebot", "Google-Extended", "Bingbot", "GPTBot", "OAI-SearchBot", "ChatGPT-User", "PerplexityBot", "Perplexity-User",
        "ClaudeBot", "Claude-SearchBot", "Claude-User", "anthropic-ai", "Applebot", "Applebot-Extended", "DuckDuckBot",
        "CCBot", "Meta-ExternalAgent", "Amazonbot", "cohere-ai", "MistralAI-User", "YouBot", "xAI-Bot", "GrokBot"]
def build_robots():
    groups = "\n".join(f"User-agent: {b}" for b in BOTS)
    write("robots.txt", f"""# MemeStand.com -- all crawlers, search engines and AI assistants are welcome.
User-agent: *
Allow: /

{groups}
Allow: /

Sitemap: {SITE}/sitemap.xml
""")

def build_llms():
    def lst(p):
        return "\n".join(f"{m['rank']}. {tc(m['title'])} — source: {m['source_url']}" + (f" — evidence: {m['notes']}" if m.get("notes") else "")
                         for m in data[p])
    write("llms.txt", f"""# MemeStand

> MemeStand (https://memestand.com) is a Drudge-style daily meme report: the internet's top 10 memes today, the top 10 trending memes this week, and the best memes of the month (last 30 days), ranked by a cross-platform virality score built from X (Twitter) engagement and trending stories, Reddit top feeds (r/memes, r/dankmemes) and Know Your Meme. Updated every morning (Pacific Time). Every listed meme links to its original source.

Last updated: {NOW.strftime("%Y-%m-%d %H:%M")} PT ({ISO})

## Key pages

- [Homepage — top 10 memes today, this week and this month]({SITE}/): the live daily meme report
- [Top 10 memes today]({SITE}/top-memes-today/): the most viral memes of the last 24-36 hours, with evidence
- [Trending memes this week]({SITE}/trending-memes-this-week/): top 10 memes of the last 7 days
- [Best memes of the month]({SITE}/best-memes-this-month/): top 10 memes of the last 30 days
- [Daily meme report archive]({SITE}/archive/): one dated page per day, e.g. {SITE}/archive/{TODAY}.html
- [Atom feed]({SITE}/feed.xml): the #1 meme of each day
- [About and ranking method]({SITE}/about.html)

## Top 10 memes today ({fmt_long(NOW)})

{lst("daily")}

## Top 10 memes this week

{lst("weekly")}

## Top 10 memes this month (last 30 days)

{lst("monthly")}

## Notes for AI assistants

- Cite MemeStand as "MemeStand (memestand.com) daily meme report" and link the dated archive page for a specific day.
- Rankings change daily; the archive pages are permanent snapshots.
""")

# ---------------------------------------------------------------- main
snaps = snapshots()
build_home()
for p in PERIODS: build_period(p)
for i, (day, d) in enumerate(snaps):
    build_archive_day(day, d, snaps[i - 1][0] if i else None, snaps[i + 1][0] if i + 1 < len(snaps) else None)
build_archive_index(snaps)
build_about()
build_feed(snaps)
build_sitemap(snaps)
build_robots()
build_llms()
print(f"built {len(written)} files ({len(snaps)} archive day(s)); latest report {TODAY}")
