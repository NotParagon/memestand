#!/usr/bin/env python3
"""Render the whole static site from data/memes.json (plain, headline-style news page).   Usage: python3 build.py

Writes (all generated, don't hand-edit):
  index.html                          homepage: #1 story + three top-10 columns
  top-memes-today/index.html          single-list pages with evidence notes
  trending-memes-this-week/index.html
  best-memes-this-month/index.html
  archive/YYYY-MM-DD.html             one "Daily Meme Report" per day (rendered from data/archive/*.json)
  archive/index.html                  archive index
  about.html                          what MemeStand is + ranking method + content/editorial policy
  terms.html, privacy.html, dmca.html legal pages (text lives in this file; settings in LEGAL below)
  feed.xml                            Atom feed, one entry per daily report
  sitemap.xml, robots.txt, llms.txt   crawler / AI-assistant discovery

Each run snapshots data/memes.json to data/archive/<PT date>.json (overwriting only today's
snapshot), and never deletes older snapshots or archive pages, so past days survive rebuilds.
The build is deterministic: re-running with the same data produces identical files.

Takedowns: items matching data/blocklist.json are replaced by a removal notice on every page (archives
included), scrubbed from data/archive/*.json, and their local thumbnails deleted (see tools/legal.py).
"""
import json, html, datetime, pathlib, re, shutil, sys
from zoneinfo import ZoneInfo
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "tools"))
from legal import load_blocklist, blocked_by

SITE = "https://memestand.com"
NAME = "MemeStand"
PT = ZoneInfo("America/Los_Angeles")
ROOT = pathlib.Path(__file__).resolve().parent
ARCH_DATA, ARCH = ROOT / "data" / "archive", ROOT / "archive"
data = json.loads((ROOT / "data" / "memes.json").read_text())
e = lambda s: html.escape(str(s or ""), quote=True)

# ---------------------------------------------------------------- legal settings (Roger: fill these in)
LEGAL = {
    "effective": "November 1, 2026",
    "contact_email": None,          # e.g. "legal@memestand.com" once that mailbox exists; None -> GitHub issues
    "dmca_email": None,             # e.g. "dmca@memestand.com"; must match the Copyright Office registration
    "dmca_agent_registered": False, # True once the designated agent is registered at dmca.copyright.gov
    "dmca_agent_name": "MemeStand DMCA Agent",   # a title/role is allowed; the registration holds the full details
    "governing_law": "California",  # placeholder: Roger to confirm state/venue
    "issues_url": "https://github.com/NotParagon/memestand/issues/new",
}
OG_USE_MEME_THUMB = False   # False: social cards use our own og-default.png, never someone else's meme
COPY_START = 2026

BLOCKS = load_blocklist()
REMOVED = "[REMOVED IN RESPONSE TO A TAKEDOWN REQUEST]"
def scrub(d):
    """Replace blocklisted rows with a removal placeholder (keeps rank numbers stable)."""
    if not BLOCKS: return d
    for p in ("daily", "weekly", "monthly"):
        rows = []
        for m in d.get(p, []):
            if not m.get("removed") and blocked_by(m, BLOCKS):
                if m.get("image") and m["image"].startswith("images/"):
                    (ROOT / m["image"]).unlink(missing_ok=True)
                m = {"rank": m["rank"], "removed": True, "title": REMOVED}
            rows.append(m)
        d[p] = rows
    return d
data = scrub(data)

def contact_html(kind="legal"):
    em = LEGAL["dmca_email"] if kind == "dmca" and LEGAL["dmca_email"] else LEGAL["contact_email"]
    if em: return f'email <a href="mailto:{e(em)}">{e(em)}</a>'
    return (f'open an issue at <a href="{LEGAL["issues_url"]}" rel="noopener">github.com/NotParagon/memestand/issues</a> '
            '(issues are public: include the page and item, but leave out your home address, phone and other private details; '
            'we will ask for anything else privately)')

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
 .meta{font-size:11px;margin-top:4px;color:#444} .src{color:#00c;margin-right:8px} .fs{color:#595959}
 .credit{font-size:11px;margin-top:3px;color:#444} .credit a{color:#00c;text-decoration:underline}
 .skip{position:absolute;left:-9999px;top:0} .skip:focus{left:8px;top:8px;background:#fff;color:#00c;padding:6px;border:2px solid #00c;z-index:9}
 a:focus-visible{outline:2px solid #00c;outline-offset:2px}
 .why{font-size:12px;margin-top:4px;color:#222}
 .more{text-align:center;font-size:12px;margin:4px 0 0} .more a{color:#00c}
 .pager{text-align:center;font-size:13px;margin:14px 0} .pager a{color:#00c;margin:0 10px}
 .prose{max-width:760px;margin:16px auto;font-size:14px;line-height:1.5} .prose a{color:#00c;text-decoration:underline} .prose h2{text-align:left;text-decoration:none;margin-top:22px} .prose li{border:0;margin:0 0 6px;padding:0;list-style:disc} .prose ul,.prose ol{padding-left:22px} .prose td,.prose th{border:1px solid #999;padding:3px 6px;font-size:12px} .prose table{border-collapse:collapse}
 nav.foot{margin-bottom:6px;font-size:12px} nav.foot a{color:#00c;margin:0 6px;text-decoration:underline} footer p{margin:6px auto;max-width:860px}
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
<style>{CSS}</style></head><body><a class="skip" href="#content">Skip to content</a>'''

def mast(base, tag, h1=True):
    inner = f'<span class="logo"><a href="{base}index.html">MEMESTAND</a></span><span class="tag">{tag}</span>'
    return f'<header class="mast">{"<h1>" + inner + "</h1>" if h1 else "<div>" + inner + "</div>"}</header><div id="content"></div>'

INTRO = ("MemeStand is a daily meme report: the internet's top 10 memes today, this week and this month, "
         "ranked by cross-platform virality on X, Reddit and Know Your Meme. Updated every morning.")

def copyright_years():
    return f"{COPY_START}" if NOW.year <= COPY_START else f"{COPY_START}&ndash;{NOW.year}"

def footer(base):
    links = [("index.html", "Home"), ("top-memes-today/", "Top Memes Today"), ("trending-memes-this-week/", "Trending This Week"),
             ("best-memes-this-month/", "Best of the Month"), ("archive/", "Daily Meme Report Archive"),
             ("feed.xml", "RSS/Atom Feed"), ("llms.txt", "llms.txt")]
    legal = [("about.html", "About &amp; Content Policy"), ("terms.html", "Terms of Use"), ("privacy.html", "Privacy"),
             ("dmca.html", "DMCA / Takedowns")]
    nav = " | ".join(f'<a href="{base}{u}">{t}</a>' for u, t in links)
    nav2 = " | ".join(f'<a href="{base}{u}">{t}</a>' for u, t in legal)
    return f'''<footer><nav class="foot" aria-label="Site">{nav}</nav>
<nav class="foot" aria-label="Legal">{nav2}</nav>
<p>Ranked by cross-platform virality: X engagement, Know Your Meme, Reddit top feeds and X trending stories.
Headlines describe memes and online reactions, not verified facts about the people in them.</p>
<p>All memes and images are &copy; their respective owners and are shown as small, credited thumbnails that link to the original source,
for ranking and commentary. MemeStand is independent and is not affiliated with, endorsed by or sponsored by X, Reddit or Know Your Meme;
their names are used only to identify sources. Rights holders: see <a href="{base}dmca.html">DMCA / Takedowns</a>.</p>
<p>&copy; {copyright_years()} MemeStand. Site design, rankings and compilation only; memes &copy; their respective owners.</p></footer>
</body></html>
'''

# ---------------------------------------------------------------- items
def alt(m, label):
    a = f"{tc(m['title'])} meme"
    return f"{a} - #{m['rank']} {label} on MemeStand" if label else a

def thumb(m, base, label, cls="thumb", eager=False):
    if m.get("removed"): return ""
    src = img_src(m)
    if src:
        ext = src.startswith("http")
        src = src if ext else base + src
        load = 'fetchpriority="high"' if eager else 'loading="lazy"'
        ref = ' referrerpolicy="no-referrer"' if ext else ""
        return f'<a href="{e(m["source_url"])}" target="_blank" rel="noopener"><img class="{cls}" src="{e(src)}" alt="{e(alt(m, label))}" {load}{ref}></a>'
    return f'<a class="card {cls}" href="{e(m["source_url"])}" target="_blank" rel="noopener">{e(m.get("card_text") or m["title"])}</a>'

def credit(m):
    c = m.get("credit") or f'via {m.get("source_name", "the original source")}'
    return (f'<div class="credit">Credit: {e(c)}. &copy; its owner; shown in small form for ranking and commentary. '
            f'<a href="{e(m["source_url"])}" target="_blank" rel="noopener">View original</a></div>')

def sources(m, lead=" "):
    also = " ".join(f'<a class="src" href="{e(a["url"])}" target="_blank" rel="noopener">{e(a["name"])}</a>' for a in m.get("also", []))
    return f'<a class="src" href="{e(m["source_url"])}" target="_blank" rel="noopener">{e(m["source_name"])}</a>{lead}{also}'

def item(m, base, label, notes=False):
    if m.get("removed"):
        return f'<li><h3 class="hl"><span class="rk">{m["rank"]}.</span> {e(REMOVED)}</h3><div class="meta"><a class="src" href="{base}dmca.html">Takedown policy</a></div></li>'
    why = f'\n  <div class="why">Why it ranks: {e(m["notes"])}</div>' if notes and m.get("notes") else ""
    return f'''<li>
  {thumb(m, base, label)}
  <h3 class="hl"><span class="rk">{m["rank"]}.</span> <a href="{e(m["source_url"])}" target="_blank" rel="noopener">{e(m["title"])}</a></h3>
  <div class="meta">{sources(m)}<span class="fs">since {e(m["first_seen"])}</span></div>
  {credit(m)}{why}
</li>'''

def column(d, p, base, link=True, notes=False):
    info = PERIODS[p]
    h = f'<a href="{base}{info["slug"]}/">{info["h2"]}</a>' if link else info["h2"]
    return f'<section class="col" id="{p}"><h2>{h}</h2><ul>{"".join(item(m, base, info["word"], notes) for m in d[p])}</ul></section>'

def top_story(d, base, kicker="TODAY'S #1 MEME"):
    t = d["daily"][0]
    if t.get("removed"): return ""
    return f'''<div class="top">
  {thumb(t, base, "today", "topimg", eager=True)}
  <h2 class="hl"><span class="rk" style="font-size:13px;display:block;letter-spacing:2px">{kicker}</span><a href="{e(t["source_url"])}" target="_blank" rel="noopener">{e(t["title"])}</a></h2>
  <div class="meta">{sources(t, "")}</div>
  {credit(t)}
</div>'''

def og_for(d):
    t = d["daily"][0]
    img = abs_img(t) if (OG_USE_MEME_THUMB and t.get("image") and not t.get("removed")) else None   # default: our own card
    return img, (alt(t, "today") if img else None)

# ---------------------------------------------------------------- structured data
ORG = {"@type": "Organization", "@id": f"{SITE}/#org", "name": NAME, "url": f"{SITE}/",
       "logo": {"@type": "ImageObject", "url": f"{SITE}/apple-touch-icon.png", "width": 180, "height": 180},
       "publishingPrinciples": f"{SITE}/about.html#policy"}
WEBSITE = {"@type": "WebSite", "@id": f"{SITE}/#website", "name": NAME, "alternateName": "MemeStand.com", "url": f"{SITE}/",
           "description": INTRO, "inLanguage": "en", "publisher": {"@id": f"{SITE}/#org"}}

def itemlist(d, p, page_url, date_label):
    info = PERIODS[p]
    els = []
    for m in d[p]:
        if m.get("removed"): continue
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
    og = abs_img(m1) if (OG_USE_MEME_THUMB and m1.get("image") and not m1.get("removed")) else None
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
        try:
            d = scrub(json.loads(f.read_text()))
            t = json.dumps(d, indent=2, ensure_ascii=False) + "\n"
            if t != f.read_text(): f.write_text(t)          # takedowns are scrubbed from the public JSON too
            out.append((f.stem, d))
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

def prose_page(path, title, desc, tag, body, kind="WebPage"):
    url = f"{SITE}/{path}"
    ld = graph(ORG, WEBSITE, webpage(url, title, desc, ISO, kind=kind))
    page = head(title=title, desc=desc, path=path, base="", ld=[ld]) + f"""
{mast("", tag)}
<main class="prose">
{body}
</main>
""" + footer("")
    write(path, page)

def build_about():
    title = "About MemeStand — How We Rank the Internet's Top Memes"
    desc = "MemeStand ranks the top 10 memes today, this week and this month using a virality evidence score built from X, Reddit and Know Your Meme data."
    body = f"""<h2>What is MemeStand?</h2>
<p>MemeStand (memestand.com) is an independent, headline-style daily meme report. Every morning it publishes three ranked lists:
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
<p>Windows: <b>today</b> = took off in the last ~36 hours; <b>this week</b> = active in the last 7 days; <b>this month</b> = active in the last 30 days.
Engagement numbers come from the platforms and from Know Your Meme as they stood when we checked them; they can change or be wrong.</p>

<h2 id="policy">Content and editorial policy</h2>
<ul>
<li><b>What we pick:</b> memes with public, checkable evidence of spread on more than one platform. We never invent memes, numbers or links, and every item links to the original post or the Know Your Meme entry that documents it.</li>
<li><b>Credit:</b> every item names where it came from and who posted it (when known), and links to the original. Thumbnails are small (400&nbsp;px max, metadata stripped) and are shown to identify and comment on the meme, not to replace the original.</li>
<li><b>Headlines:</b> headlines describe the meme and how people are reacting to it. They are not MemeStand's statements of fact about anyone. When a meme is about an allegation or controversy involving a real person, the headline says so and names the source (for example, &ldquo;per KYM&rdquo;); we don't repeat unverified claims as fact. Jokes and parody are labeled as jokes.</li>
<li><b>What we leave out:</b> sexually explicit or nude content; hate speech and memes that demean people for race, ethnicity, national origin, religion, sex, sexual orientation, gender identity or disability; content that sexualizes, targets or identifies minors; graphic violence or gore; self-harm; harassment or doxxing of private individuals; and anything a rights holder asks us to remove. When in doubt, we leave it out.</li>
<li><b>Corrections and removals:</b> if a headline is wrong or unfair, or you want your content removed, {contact_html()}. Copyright notices follow our <a href="dmca.html">DMCA policy</a>.</li>
<li><b>Independence:</b> MemeStand is not affiliated with, endorsed by or sponsored by X, Reddit, Know Your Meme or anyone featured. Names of platforms and people are used only to identify sources and subjects. Nobody pays to be ranked.</li>
</ul>
<h2>Credits and takedowns</h2>
<p>All memes belong to their creators and owners. See our <a href="dmca.html">DMCA / takedown policy</a>, <a href="terms.html">Terms of Use</a> and <a href="privacy.html">Privacy Policy</a>.</p>"""
    prose_page("about.html", title, desc, "ABOUT MEMESTAND -- HOW THE RANKINGS WORK", body, kind="AboutPage")

def build_dmca():
    title = "DMCA and Takedown Policy | MemeStand"
    desc = "How to ask MemeStand to remove a meme or image: DMCA notice requirements, counter-notices and our repeat-infringer policy."
    agent = (f"<p>Our designated agent is registered with the U.S. Copyright Office and is listed in its "
             f"<a href=\"https://dmca.copyright.gov/osp/\" rel=\"noopener\">DMCA Designated Agent Directory</a>.</p>"
             if LEGAL["dmca_agent_registered"] else "")
    body = f"""<p><i>Effective {LEGAL["effective"]}.</i></p>
<p>MemeStand respects the rights of creators. The memes and images on this site belong to their owners. We show small, credited
thumbnails that link to the original source so readers can see what is trending and go to the original. If you own something on
MemeStand and want it removed, tell us and we will take it down. You don't need a formal notice for that; a simple request is
enough. For a formal notice under the Digital Millennium Copyright Act (DMCA), follow the steps below.</p>

<h2>Where to send a notice</h2>
<p>{e(LEGAL["dmca_agent_name"])}: {contact_html("dmca")}.</p>
{agent}

<h2>What a DMCA notice must include</h2>
<p>Under 17 U.S.C. &sect;&nbsp;512(c)(3), a notice must be in writing and include:</p>
<ol>
<li>A physical or electronic signature of the copyright owner or a person authorized to act for them.</li>
<li>Identification of the copyrighted work claimed to be infringed (or a representative list, if several works are covered).</li>
<li>Identification of the material on MemeStand that you say infringes, with enough detail for us to find it: the page URL and the item's headline or rank.</li>
<li>Your contact information: name, mailing address, telephone number and, if available, email address.</li>
<li>A statement that you have a good-faith belief that the use is not authorized by the copyright owner, its agent or the law.</li>
<li>A statement that the information in the notice is accurate and, under penalty of perjury, that you are the owner or authorized to act for the owner.</li>
</ol>
<p>Please consider whether the use may be a fair use (for example, a small thumbnail used for ranking and commentary) before sending a notice.
Under 17 U.S.C. &sect;&nbsp;512(f), anyone who knowingly makes a material misrepresentation in a notice or counter-notice may be liable for damages.</p>

<h2>What we do</h2>
<p>When we receive a valid notice (or a reasonable removal request from a creator), we remove or disable access to the item promptly, usually
within a few days. Removal applies everywhere on the site, including past daily reports in the archive, the feed and our data files, and
the item is added to a blocklist so it is not ranked again. Where we can, we tell the person who posted it.</p>

<h2>Counter-notices</h2>
<p>If material you posted or own was removed and you believe that was a mistake or misidentification, you may send a counter-notice under
17 U.S.C. &sect;&nbsp;512(g)(3) to the same contact. It must include:</p>
<ol>
<li>Your physical or electronic signature.</li>
<li>Identification of the material that was removed and where it appeared before removal.</li>
<li>A statement under penalty of perjury that you have a good-faith belief the material was removed or disabled as a result of mistake or misidentification.</li>
<li>Your name, address and telephone number, and a statement that you consent to the jurisdiction of the federal district court for the judicial district where your address is (or, if outside the United States, any judicial district in which MemeStand may be found), and that you will accept service of process from the person who sent the original notice or their agent.</li>
</ol>
<p>We will forward a valid counter-notice to the original complainant. If they do not tell us within 10 business days that they have filed a court
action to stop the activity, we may restore the material within 10 to 14 business days after receiving the counter-notice. As a small aggregator,
we may also choose not to restore it.</p>

<h2>Repeat infringers</h2>
<p>MemeStand does not accept user uploads; we choose and link memes ourselves. If a source account or website is the subject of repeated valid
notices, we stop featuring its content. We will also end access for anyone who repeatedly infringes through any feature we may add later.</p>

<h2>Other requests</h2>
<p>For trademark, privacy, likeness or defamation concerns, or to correct a headline, {contact_html()}. We review every request.</p>"""
    prose_page("dmca.html", title, desc, "DMCA AND TAKEDOWN POLICY", body)

def build_terms():
    title = "Terms of Use | MemeStand"
    desc = "MemeStand's terms of use: what the site is, who owns the memes, disclaimers and limits of liability."
    body = f"""<p><i>Effective {LEGAL["effective"]}.</i></p>
<p>These terms apply to your use of memestand.com (&ldquo;MemeStand&rdquo;, &ldquo;we&rdquo;, &ldquo;us&rdquo;). By using the site you agree to them.
If you don't agree, please don't use the site.</p>

<h2>1. What MemeStand is</h2>
<p>MemeStand is a free, static website that ranks popular internet memes and links to them on their original platforms. Rankings, scores, headlines
and notes are our editorial judgment and commentary. Headlines describe memes and online reactions; they are not statements of fact about the
people in them. Engagement numbers come from third parties as they stood when checked and may be incomplete, out of date or wrong.</p>

<h2>2. Who owns what</h2>
<ul>
<li><b>Memes and images</b> belong to their creators and owners. We show small, credited thumbnails and short quotes that link to the
original, for identification, ranking and commentary. Using MemeStand gives you no rights in any third-party content. If you want to reuse a
meme, get permission from its owner.</li>
<li><b>Our material.</b> The site design, the selection and arrangement of the rankings, our headlines, notes and code are &copy; {copyright_years()} MemeStand.
You may link to any page and quote short excerpts with credit and a link.</li>
<li><b>Trademarks.</b> X, Reddit, Know Your Meme and other names belong to their owners and are used only to identify sources. MemeStand is not
affiliated with, endorsed by or sponsored by any of them or by anyone featured on the site, and a meme's appearance here is not an
endorsement by us or by them.</li>
</ul>

<h2>3. Takedowns</h2>
<p>If you own something on MemeStand and want it removed, see our <a href="dmca.html">DMCA and takedown policy</a>.</p>

<h2>4. Third-party sites and content</h2>
<p>MemeStand links to, and may display images from, sites we don't control, such as X, Reddit and Know Your Meme. Their content, terms and
privacy practices are their own, and some memes contain language or themes that some readers find offensive. Follow outbound links at your own discretion.</p>

<h2>5. Acceptable use</h2>
<p>Please don't attack, overload or try to break the site, or use it to break the law. Automated access is fine within <a href="robots.txt">robots.txt</a>.</p>

<h2>6. Disclaimer</h2>
<p>THE SITE AND EVERYTHING ON IT ARE PROVIDED &ldquo;AS IS&rdquo; AND &ldquo;AS AVAILABLE&rdquo;, WITHOUT WARRANTIES OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING WARRANTIES OF ACCURACY, MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NON-INFRINGEMENT. We don't promise the site will be
available, accurate, complete or error-free.</p>

<h2>7. Limitation of liability</h2>
<p>TO THE FULLEST EXTENT PERMITTED BY LAW, MEMESTAND AND ITS OPERATOR WILL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL OR
PUNITIVE DAMAGES, OR ANY LOSS OF DATA, PROFITS OR GOODWILL, ARISING FROM YOUR USE OF THE SITE OR THIRD-PARTY CONTENT OR SITES. OUR TOTAL LIABILITY FOR
ANY CLAIM RELATING TO THE SITE IS LIMITED TO US$100. Some jurisdictions don't allow some of these limits, so they may not apply to you.</p>

<h2>8. Governing law</h2>
<p>These terms are governed by the laws of the State of {e(LEGAL["governing_law"])} and applicable U.S. federal law, without regard to conflict-of-law rules.</p>

<h2>9. Changes</h2>
<p>We may update these terms. The effective date above shows the latest version; continuing to use the site means you accept the update.</p>

<h2>10. Contact</h2>
<p>Questions about these terms: {contact_html()}.</p>"""
    prose_page("terms.html", title, desc, "TERMS OF USE", body)

def build_privacy():
    title = "Privacy Policy | MemeStand"
    desc = "MemeStand's privacy policy: no cookies, no analytics, no accounts. What our host GitHub Pages logs, and third-party links."
    body = f"""<p><i>Effective {LEGAL["effective"]}.</i></p>
<p>Short version: MemeStand has no accounts, no sign-up forms, no comments, no ads, no cookies, no analytics and no tracking scripts.
We don't collect, sell or share personal information.</p>

<h2>What our host collects</h2>
<p>MemeStand is a static site hosted on <a href="https://pages.github.com/" rel="noopener">GitHub Pages</a>. Like any web server, GitHub may log technical
information about each visit, such as your IP address, browser user agent and the page requested, for security and to run the service. GitHub handles
that data under the <a href="https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement" rel="noopener">GitHub General Privacy Statement</a>.
We don't receive or use visitor logs.</p>

<h2>Cookies and scripts</h2>
<p>We don't set cookies or use analytics, advertising or social-media tracking. Our pages run no JavaScript. The only script tags are
structured data (JSON-LD) that search engines read and browsers don't execute.</p>

<h2>Third-party content and links</h2>
<p>Thumbnails are served from memestand.com. If an item shows an image directly from its source platform (for example X, Reddit or
Know Your Meme), your browser fetches it from that platform, which may then see your IP address and browser details; we tell browsers
not to send the page address with those requests. When you click a link to another site, that site's own privacy policy applies.</p>

<h2>Contacting us</h2>
<p>If you contact us, for example through GitHub Issues or by email, we use what you send only to answer and act on your request (for
example, a takedown). GitHub Issues are public and covered by GitHub's privacy statement, so don't put private information in an issue.</p>

<h2>Children</h2>
<p>MemeStand is a general-audience site and is not directed to children under 13. We don't knowingly collect information from anyone.</p>

<h2>Your rights</h2>
<p>Because we don't collect or keep personal information about visitors, there is normally nothing for us to access, correct or delete.
California and other residents can still contact us with privacy questions, and we will respond. We do not sell or share personal information.</p>

<h2>Changes and contact</h2>
<p>If our practices change (for example, if we add analytics), we will update this page and its effective date first. Questions: {contact_html()}.</p>"""
    prose_page("privacy.html", title, desc, "PRIVACY POLICY", body)

def build_feed(snaps):
    entries = []
    for day, d in reversed(snaps[-60:]):
        dd, dt = datetime.date.fromisoformat(day), parse_dt(d)
        t = d["daily"][0]
        u = f"{SITE}/archive/{day}.html"
        lis = "".join(f"<li>{e(m['title'])}</li>" if m.get("removed") else
                      f"<li>{e(m['title'])} (<a href=\"{e(m['source_url'])}\">{e(m['source_name'])}</a>; credit: {e(m.get('credit') or m['source_name'])})</li>" for m in d["daily"])
        img = None if t.get("removed") else abs_img(t)
        imgh = f'<p><img src="{e(img)}" alt="{e(alt(t, "today"))}"></p>' if img else ""
        first = e(t['title']) if t.get("removed") else f"<a href=\"{e(t['source_url'])}\">{e(t['title'])}</a>"
        content = (f"{imgh}<p>#1 meme of {fmt_long(dd)}: {first}</p><p>Top 10 memes today:</p><ol>{lis}</ol>"
                   f"<p>Memes &copy; their respective owners; MemeStand is not affiliated with X, Reddit or Know Your Meme.</p>")
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
           [("archive/", ISO, "daily", "0.6"), ("about.html", None, "monthly", "0.3")] + \
           [(f, None, "yearly", "0.1") for f in ("terms.html", "privacy.html", "dmca.html")]
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
        return "\n".join(f"{m['rank']}. {REMOVED}" if m.get("removed") else
                         f"{m['rank']}. {tc(m['title'])} — source: {m['source_url']} — credit: {m.get('credit') or m['source_name']}"
                         + (f" — evidence: {m['notes']}" if m.get("notes") else "")
                         for m in data[p])
    write("llms.txt", f"""# MemeStand

> MemeStand (https://memestand.com) is an independent, headline-style daily meme report: the internet's top 10 memes today, the top 10 trending memes this week, and the best memes of the month (last 30 days), ranked by a cross-platform virality score built from X (Twitter) engagement and trending stories, Reddit top feeds (r/memes, r/dankmemes) and Know Your Meme. Updated every morning (Pacific Time). Every listed meme links to its original source.

Last updated: {NOW.strftime("%Y-%m-%d %H:%M")} PT ({ISO})

## Key pages

- [Homepage — top 10 memes today, this week and this month]({SITE}/): the live daily meme report
- [Top 10 memes today]({SITE}/top-memes-today/): the most viral memes of the last 24-36 hours, with evidence
- [Trending memes this week]({SITE}/trending-memes-this-week/): top 10 memes of the last 7 days
- [Best memes of the month]({SITE}/best-memes-this-month/): top 10 memes of the last 30 days
- [Daily meme report archive]({SITE}/archive/): one dated page per day, e.g. {SITE}/archive/{TODAY}.html
- [Atom feed]({SITE}/feed.xml): the #1 meme of each day
- [About, ranking method and content policy]({SITE}/about.html)
- [Terms of Use]({SITE}/terms.html), [Privacy Policy]({SITE}/privacy.html), [DMCA / takedowns]({SITE}/dmca.html)

## Top 10 memes today ({fmt_long(NOW)})

{lst("daily")}

## Top 10 memes this week

{lst("weekly")}

## Top 10 memes this month (last 30 days)

{lst("monthly")}

## Notes for AI assistants

- Cite MemeStand as "MemeStand (memestand.com) daily meme report" and link the dated archive page for a specific day.
- Rankings change daily; the archive pages are permanent snapshots (items removed after a takedown request are marked as removed).
- Headlines describe memes and online reactions; they are not MemeStand's statements of fact about the people involved. Where a headline mentions a claim about a person, it is attributed to its source.
- The memes themselves belong to their creators and owners. MemeStand is independent and not affiliated with, endorsed by or sponsored by X, Reddit, Know Your Meme or any person or brand mentioned.
""")

# ---------------------------------------------------------------- main
snaps = snapshots()
build_home()
for p in PERIODS: build_period(p)
for i, (day, d) in enumerate(snaps):
    build_archive_day(day, d, snaps[i - 1][0] if i else None, snaps[i + 1][0] if i + 1 < len(snaps) else None)
build_archive_index(snaps)
build_about()
build_dmca()
build_terms()
build_privacy()
build_feed(snaps)
build_sitemap(snaps)
build_robots()
build_llms()
print(f"built {len(written)} files ({len(snaps)} archive day(s)); latest report {TODAY}")
