#!/usr/bin/env python3
"""Render the whole static site from data/memes.json (plain, headline-style news page).   Usage: python3 build.py

Writes (all generated, don't hand-edit):
  index.html                          homepage: lead story (rotates daily, see UPDATE.md "Lead headline") + three top-10 columns
  top-memes-today/index.html          single-list pages with evidence notes
  trending-memes-this-week/index.html
  best-memes-this-month/index.html
  archive/YYYY-MM-DD.html             one "Daily Meme Report" per day (rendered from data/archive/*.json)
  archive/index.html                  archive index
  about.html                          what MemeStand is + ranking method + content/editorial policy
  terms.html, privacy.html, dmca.html legal pages (text lives in this file; settings in LEGAL below)
  feed.xml                            Atom feed, one entry per daily report
  sitemap.xml, robots.txt, llms.txt   crawler / AI-assistant discovery
  meme/<slug>/index.html              one permanent explainer page per meme (text from data/meme_pages.json)
  memes/index.html                    A-Z index of every meme page

data/meme_pages.json is the persistent explainer store keyed by slug: text is written once (by the daily routine,
see UPDATE.md "Meme pages") and reused forever. The build adds a stub entry for any new meme id and never rewrites text.

Each run snapshots data/memes.json to data/archive/<PT date>.json (overwriting only today's
snapshot), and never deletes older snapshots or archive pages, so past days survive rebuilds.
The build is deterministic: re-running with the same data produces identical files.

Takedowns: items matching data/blocklist.json are replaced by a removal notice on every page (archives
included), scrubbed from data/archive/*.json, and their local thumbnails deleted (see tools/legal.py).
Blocked memes also lose their meme page and their entry in data/meme_pages.json.
"""
import json, html, datetime, pathlib, re, shutil, sys
from zoneinfo import ZoneInfo
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "tools"))
from legal import load_blocklist, blocked_by, exclusion_reason

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
    "contact_email": "hello@memestand.com",   # site contact email everywhere (footer, about, privacy, terms, DMCA); None -> GitHub issues
    "dmca_email": "hello@memestand.com",      # DMCA/takedown contact; must match the Copyright Office registration
    "dmca_agent_registered": False, # True once the designated agent is registered at dmca.copyright.gov
    "dmca_agent_name": "MemeStand DMCA Agent",   # a title/role is allowed; the registration holds the full details
    "governing_law": "California",  # placeholder: Roger to confirm state/venue
    "issues_url": "https://github.com/NotParagon/memestand/issues/new",
}
OG_USE_MEME_THUMB = False   # False: social cards use our own og-default.png, never someone else's meme
COPY_START = 2026
# Cloudflare Web Analytics beacon (cookieless; public site token). Goes just before </body> on EVERY page via footer(). Keep it.
CF_ANALYTICS = '''<!-- Cloudflare Web Analytics --><script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{"token": "7fe3f90e5dc444b9a67ecfce9aed6c1e"}'></script><!-- End Cloudflare Web Analytics -->'''
PRIVACY_UPDATED = "November 1, 2026"   # bump when the privacy policy text changes

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
 *,*::before,*::after{box-sizing:border-box}
 html{-webkit-text-size-adjust:100%;text-size-adjust:100%}
 body{background:#fff;color:#000;font-family:"Courier New",Courier,monospace;margin:0 auto;max-width:1180px;padding:10px 16px 40px;overflow-wrap:break-word}
 img{max-width:100%;height:auto}
 a{color:#000;text-decoration:none} a:hover{text-decoration:underline}
 .mast{text-align:center;border-bottom:3px double #000;padding-bottom:8px}
 .mast h1{margin:6px 0 0;font-weight:bold;font-size:inherit}
 .mast .logo{display:block;font-size:56px;letter-spacing:4px} .mast .logo a{color:#000}
 .mast .tag{display:block;font-size:13px;letter-spacing:2px;font-weight:normal}
 .intro{text-align:center;font-size:12px;margin:6px auto 0;max-width:820px;color:#333}
 .upd{text-align:center;font-size:12px;margin:6px 0 2px}
 .top{text-align:center;margin:18px auto 30px;max-width:900px;padding-bottom:22px;border-bottom:3px double #000}
 .top img{max-width:100%;max-height:520px;border:1px solid #000}
 .top .card{min-height:240px;font-size:28px}
 .top h2{margin:10px 0 0;text-decoration:none}
 .top .hl a{color:#c00;font-size:40px;font-weight:bold;line-height:1.12;text-transform:uppercase}
 .top .kick{display:block;font-size:13px;letter-spacing:2px;color:#c00;margin-bottom:4px}
 .top .meta{margin-top:6px}
 .grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0;margin-top:10px}
 .grid .col{padding:0 20px;min-width:0} .grid .col:first-child{padding-left:0} .grid .col:last-child{padding-right:0}
 .grid .col+.col{border-left:2px solid #000}
 .one{max-width:640px;margin:10px auto 0}
 .col{margin-bottom:10px}
 .col>h2{position:sticky;top:0;z-index:5;margin:0 0 16px;padding:11px 12px;background:#000;color:#fff;font-size:18px;line-height:1.2;
   letter-spacing:2px;text-transform:uppercase;text-align:center;text-decoration:none;border-bottom:5px solid #c00}
 #weekly>h2{border-bottom-color:#00c} #monthly>h2{border-bottom-color:#080}
 .col>h2 a{color:#fff;display:block} .col>h2 a::after{content:" \\203A"}
 h2{font-size:20px;text-align:center;text-decoration:underline;margin:6px 0 12px} h2 a{color:#000}
 h3{margin:0;font-size:inherit}
 ul{list-style:none;padding:0;margin:0}
 li{margin:0 0 22px;padding:12px;border:1px solid #bbb;border-top:3px solid #000;background:#fff;box-shadow:0 2px 4px rgba(0,0,0,.10)}
 .thumb{display:block;width:100%;max-height:260px;object-fit:contain;background:#f3f3f3;border:1px solid #ccc;margin-bottom:10px}
 .one .thumb{max-height:420px}
 .card{display:flex;align-items:center;justify-content:center;text-align:center;min-height:120px;padding:14px;border:2px solid #000;font-weight:bold;font-size:17px;background:#fff}
 .hl{font-size:16px;font-weight:bold;line-height:1.25;text-transform:uppercase}
 .rk{color:#c00}
 li .hl .rk{display:inline-block;min-width:2.1em;margin-right:2px;padding:2px 6px;background:#c00;color:#fff;text-align:center;line-height:1.3}
 .meta{font-size:11px;margin-top:6px;color:#444} .src{color:#00c;margin-right:8px} .fs{color:#595959}
 .credit{font-size:11px;margin-top:4px;color:#444} .credit a{color:#00c;text-decoration:underline}
 .skip{position:absolute;left:-9999px;top:0} .skip:focus{left:8px;top:8px;background:#fff;color:#00c;padding:6px;border:2px solid #00c;z-index:9}
 a:focus-visible{outline:2px solid #00c;outline-offset:2px}
 .why{font-size:12px;margin-top:6px;color:#222}
 .more{text-align:center;font-size:12px;margin:14px 0 0} .more a{color:#00c}
 .pager{text-align:center;font-size:13px;margin:14px 0} .pager a{color:#00c;margin:0 10px}
 .prose{max-width:760px;margin:16px auto;font-size:14px;line-height:1.5} .prose a{color:#00c;text-decoration:underline} .prose h2{text-align:left;text-decoration:none;margin-top:28px;padding:7px 10px;background:#000;color:#fff;font-size:17px;letter-spacing:1px} .prose li{border:0;margin:0 0 6px;padding:0;list-style:disc;box-shadow:none;background:none} .prose ul,.prose ol{padding-left:22px} .prose td,.prose th{border:1px solid #999;padding:3px 6px;font-size:12px} .prose table{border-collapse:collapse;max-width:100%}
 nav.foot{margin-bottom:6px;font-size:12px} nav.foot a{color:#00c;margin:0 6px;text-decoration:underline} footer p{margin:6px auto;max-width:860px}
 .crumbs{font-size:12px;margin:10px auto 0;max-width:760px} .crumbs a{color:#00c;text-decoration:underline}
 .prose h1{font-size:24px;line-height:1.25;margin:10px 0 12px} .prose h3{margin:14px 0 6px} .prose .thumb{max-height:420px;max-width:400px} .prose .card{max-width:400px}
 .prose .note{font-size:12px;color:#444} .az{text-align:center;font-size:14px;margin:8px 0} .az a{color:#00c;margin:0 4px;text-decoration:underline}
 .one h2[id]{position:sticky;top:0;z-index:5;text-align:left;text-decoration:none;margin:28px 0 14px;padding:8px 12px;background:#000;color:#fff;border-bottom:5px solid #c00}
 footer{border-top:3px double #000;margin-top:28px;padding-top:10px;font-size:11px;text-align:center;color:#444}
 @media(max-width:860px){
  body{padding:8px 14px 32px}
  .mast .logo{font-size:40px;letter-spacing:3px} .mast .tag{font-size:12px;letter-spacing:1px}
  .intro{font-size:13px;line-height:1.4}
  .top{margin:14px auto 26px;padding-bottom:20px}
  .top img{max-height:60vh;width:auto}
  .top .card{min-height:0;font-size:20px;padding:18px 14px}
  .top .hl a{font-size:27px;line-height:1.15}
  .grid{display:block;margin-top:0}
  .grid .col,.grid .col:first-child,.grid .col:last-child{padding:0}
  .grid .col+.col{border-left:0;margin-top:40px;padding-top:14px;border-top:3px double #000}
  .col>h2{font-size:18px;padding:13px 10px;margin:0 0 16px} .col>h2 a{margin:-13px -10px;padding:13px 10px}
  footer p a,.prose p a,.prose .note a{padding:16px 0}
  .prose a{overflow-wrap:anywhere}
  li{margin:0 0 26px;padding:12px}
  .thumb,.one .thumb{max-height:380px}
  .card{font-size:17px}
  .hl{font-size:18px;line-height:1.3}
  .meta,.credit{font-size:13px;line-height:1.45}
  .why{font-size:14px;line-height:1.45}
  .hl a{display:inline}
  li h3.hl{min-height:44px}
  .meta{display:flex;flex-wrap:wrap;align-items:center;column-gap:12px;margin-top:4px}
  .src{display:inline-flex;align-items:center;min-height:44px;margin-right:0}
  .credit a{display:flex;align-items:center;width:fit-content;min-height:44px}
  .top .meta{justify-content:center} .top .credit a{margin:0 auto}
  .pager a,.more a,.crumbs a,.az a,nav.foot a{display:inline-block;min-height:44px;line-height:44px;padding:0 4px}
  nav.foot{font-size:13px;line-height:1.2} footer{font-size:12px}
  .prose{font-size:16px} .prose h1{font-size:22px} .prose .thumb,.prose .card{max-width:100%}
  .prose li{margin-bottom:10px} .prose li a{display:inline-block;padding:10px 0}
 }
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
             ("memes/", "Memes A&ndash;Z"), ("feed.xml", "RSS/Atom Feed"), ("llms.txt", "llms.txt")]
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
{CF_ANALYTICS}
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

def meme_href(m, base):
    """Relative link to the meme's own page, or None (removed / unknown)."""
    sl = None if m.get("removed") else SLUG.get(m.get("id"))
    return f"{base}meme/{sl}/" if sl and sl in PAGES else None

def hl_link(m, base):
    h = meme_href(m, base)
    if h: return f'<a href="{e(h)}">{e(m["title"])}</a>'
    return f'<a href="{e(m["source_url"])}" target="_blank" rel="noopener">{e(m["title"])}</a>'

def item(m, base, label, notes=False):
    if m.get("removed"):
        return f'<li><h3 class="hl"><span class="rk">{m["rank"]}.</span> {e(REMOVED)}</h3><div class="meta"><a class="src" href="{base}dmca.html">Takedown policy</a></div></li>'
    why = f'\n  <div class="why">Why it ranks: {e(m["notes"])}</div>' if notes and m.get("notes") else ""
    return f'''<li>
  {thumb(m, base, label)}
  <h3 class="hl"><span class="rk">{m["rank"]}.</span> {hl_link(m, base)}</h3>
  <div class="meta">{sources(m)}<span class="fs">since {e(m["first_seen"])}</span></div>
  {credit(m)}{why}
</li>'''

def column(d, p, base, link=True, notes=False):
    info = PERIODS[p]
    h = f'<a href="{base}{info["slug"]}/">{info["h2"]}</a>' if link else info["h2"]
    return f'<section class="col" id="{p}"><h2>{h}</h2><ul>{"".join(item(m, base, info["word"], notes) for m in d[p])}</ul></section>'

def top_story(d, base, kicker="TODAY'S LEAD MEME", day=None):
    t = lead_of(d, day or TODAY)
    if t.get("removed"): return ""
    return f'''<div class="top">
  {thumb(t, base, "today", "topimg", eager=True)}
  <h2 class="hl"><span class="kick">{kicker}</span>{hl_link(t, base)}</h2>
  <div class="meta">{sources(t, "")}</div>
  {credit(t)}
</div>'''

def og_for(d, day=None):
    t = lead_of(d, day or TODAY)
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
        h = meme_href(m, "")
        li = {"@type": "ListItem", "position": m["rank"], "name": tc(m["title"]), "url": f"{SITE}/{h}" if h else m["source_url"]}
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

# ---------------------------------------------------------------- meme pages (/meme/<slug>/) + A-Z index
STORE = ROOT / "data" / "meme_pages.json"
STORE_DOC = ("Persistent per-meme explainer store for the /meme/<slug>/ pages, keyed by slug. build.py reads it and never regenerates written text. "
             "ids = candidate ids that map to this page (keep the slug forever). status: 'full' (real explanation + origin with sources) or 'short' "
             "(only what is known). Text must follow UPDATE.md 'Legal rules' and 'Meme pages': neutral, factual, attributed, no invented origins. "
             "build.py adds a stub (explainer null) for any new meme; the daily routine fills it in.")
SLUG, PAGES = {}, {}          # candidate id -> slug ; slug -> page info
PERIOD_ORDER = {"daily": 0, "weekly": 1, "monthly": 2}

# ---------------------------------------------------------------- lead headline (the big top story)
# Rule (UPDATE.md "Lead headline"): the lead is today's highest-ranked daily meme that has NOT been the lead on any of the
# previous LEAD_WINDOW days; a meme that is new on MemeStand today (in no earlier snapshot) is preferred if it is in the
# daily top 3; if every candidate was a recent lead, fall back to the daily #1. Candidates must pass the blocklist and
# legal rules. The ranked top-10 lists are untouched. Past leads persist in data/lead_history.json (date -> meme slug);
# days missing from it are seeded from their archive snapshot's daily #1 (the old rule). Today's entry is recomputed
# from the previous days only, so rebuilding on the same day is idempotent.
LEAD_HISTORY = ROOT / "data" / "lead_history.json"
LEAD_WINDOW = 7
LEAD_DOC = ("Lead headline (big top story) per day, date -> meme slug (data/meme_pages.json). Written by build.py; past days are "
            "never changed. Used to keep the lead from repeating within 7 days. See UPDATE.md 'Lead headline'.")
LEADS = {}                    # day -> meme slug of that day's lead

def lead_key(m): return SLUG.get(m.get("id")) or m.get("id")

def lead_ok(m):
    return bool(m) and not m.get("removed") and not (BLOCKS and blocked_by(m, BLOCKS)) and exclusion_reason(m) is None

def pick_lead(day, d, recent, earlier_ids):
    rows = [m for m in d.get("daily", []) if lead_ok(m)]
    fresh = [m for m in rows if lead_key(m) not in recent]
    new_top3 = [m for m in fresh if m.get("rank", 99) <= 3 and m.get("id") not in earlier_ids]
    if new_top3: return new_top3[0], "new today, in the daily top 3"
    if fresh: return fresh[0], f"highest-ranked daily meme not led in the previous {LEAD_WINDOW} days"
    if rows: return rows[0], f"fallback: every candidate led in the previous {LEAD_WINDOW} days"
    return None, "no eligible daily meme"

def choose_leads(snaps):
    store = json.loads(LEAD_HISTORY.read_text()) if LEAD_HISTORY.exists() else {}
    hist = dict(store.get("leads", {}))
    seen_ids, why = set(), None
    for day, d in snaps:                      # oldest -> newest
        if day == TODAY:
            cut = (datetime.date.fromisoformat(day) - datetime.timedelta(days=LEAD_WINDOW)).isoformat()
            recent = {v for k, v in hist.items() if cut <= k < day}
            m, why = pick_lead(day, d, recent, seen_ids)
            if m: hist[day] = lead_key(m)
            else: hist.pop(day, None)
        elif day not in hist and d.get("daily") and not d["daily"][0].get("removed"):
            hist[day] = lead_key(d["daily"][0])   # seed: before this rule the lead was always the daily #1
        seen_ids |= {m.get("id") for p in PERIODS for m in d.get(p, []) if m.get("id")}
    LEADS.update(hist)
    txt = json.dumps({"_doc": LEAD_DOC, "window_days": LEAD_WINDOW, "leads": dict(sorted(hist.items()))}, indent=2, ensure_ascii=False) + "\n"
    if not LEAD_HISTORY.exists() or LEAD_HISTORY.read_text() != txt: LEAD_HISTORY.write_text(txt)
    return why

def lead_of(d, day):
    """The lead item for a snapshot: the history's meme if it is in that day's daily list, else the daily #1."""
    want = LEADS.get(day)
    for m in d.get("daily", []):
        if want and not m.get("removed") and lead_key(m) == want: return m
    return d["daily"][0]

def slugify(s):
    s = re.sub(r"['\u2019]", "", (s or "").lower().replace("&", " and "))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:70].rstrip("-") or "meme"

def paras(t): return [x.strip() for x in (t or "").split("\n\n") if x.strip()]

def first_sentence(t, n=158):
    p = paras(t)
    if not p: return ""
    m = re.match(r"(.+?[.!?])(\s|$)", p[0])
    s = m.group(1) if m else p[0]
    if len(s) > n: s = s[:n - 1].rsplit(" ", 1)[0].rstrip(",;:") + "\u2026"
    return s

def kym_of(m):
    if "knowyourmeme.com" in (m.get("source_url") or ""): return m["source_url"]
    return next((a["url"] for a in m.get("also", []) if "knowyourmeme.com" in a.get("url", "")), None)

def meme_registry(snaps):
    """Map every meme in every snapshot to a stable slug, add stubs for new memes, drop blocked ones."""
    store = json.loads(STORE.read_text()) if STORE.exists() else {"memes": {}}
    ents = store.get("memes", {})
    for sl in sorted(ents):        # blocked memes get no page and no stored text
        ent = ents[sl]
        probes = [{"id": i, "source_url": ent.get("source_url") or "", "title": ent.get("name") or ""} for i in (ent.get("ids") or [None])]
        if BLOCKS and any(blocked_by(x, BLOCKS) for x in probes): del ents[sl]
    for sl, ent in ents.items():
        for i in ent.get("ids", []): SLUG[i] = sl
    seen = {}
    for day, d in snaps:
        for p in PERIODS:
            for m in d.get(p, []):
                if m.get("removed") or not m.get("id"): continue
                seen.setdefault(m["id"], []).append((day, p, m))
    for mid in sorted(seen, key=lambda i: (seen[i][0][0], i)):
        latest = seen[mid][-1][2]
        if mid not in SLUG:   # new meme: stable slug from its name (or id), deduped, persisted
            name = latest.get("name") or mid.replace("-", " ").title()
            sl, n = slugify(name), 2
            while sl in ents: sl, n = f"{slugify(name)}-{n}", n + 1
            ents[sl] = {"name": name, "ids": [mid], "status": "short", "explainer": None, "origin": None,
                        "source_url": latest.get("source_url"), "kym_url": kym_of(latest), "sources": [], "related": [],
                        "written": seen[mid][0][0]}
            SLUG[mid] = sl
        ent = ents[SLUG[mid]]
        for k in ("explainer", "origin", "kym_url"):          # optional fields from data fill gaps, never overwrite
            if latest.get(k) and not ent.get(k): ent[k] = latest[k]
    txt = json.dumps({"_doc": STORE_DOC, "memes": dict(sorted(ents.items()))}, indent=2, ensure_ascii=False) + "\n"
    if not STORE.exists() or STORE.read_text() != txt: STORE.write_text(txt)
    by_slug, snapd = {}, dict(snaps)
    for mid, rows in seen.items(): by_slug.setdefault(SLUG[mid], []).extend(rows)
    for sl, rows in by_slug.items():
        ent = ents[sl]
        rows.sort(key=lambda r: (r[0], PERIOD_ORDER[r[1]], r[2]["rank"]))
        days = sorted({r[0] for r in rows})
        latest = [r for r in rows if r[0] == days[-1]][0][2]
        best = {}
        for day, p, m in rows:
            if p not in best or m["rank"] < best[p][0]: best[p] = (m["rank"], day)
        full = ent.get("status") == "full" and bool(ent.get("explainer")) and bool(ent.get("origin"))
        PAGES[sl] = {"slug": sl, "name": ent["name"], "explainer": ent.get("explainer"), "origin": ent.get("origin"),
                     "status": "full" if full else "short", "kym_url": ent.get("kym_url"),
                     "sources": ent.get("sources", []), "related": ent.get("related", []), "written": ent.get("written"),
                     "days": days, "best": best, "latest": latest, "rows": rows,
                     "published": parse_dt(snapd[days[0]]).isoformat(timespec="seconds"),
                     "modified": parse_dt(snapd[days[-1]]).isoformat(timespec="seconds"),
                     "blurb": first_sentence(ent.get("explainer")) or f"Ranked by MemeStand: {tc(latest['title'])}."}

def sort_key(name): return re.sub(r"^[^a-z0-9]+", "", name.lower())
def az_order(): return sorted(PAGES, key=lambda sl: (sort_key(PAGES[sl]["name"]), sl))

def meme_phrase(name):
    """'X meme' unless the name already ends in meme(s)/trend."""
    return name if re.search(r"\b(memes?|trend)$", name, re.I) else f"{name} meme"

def related_for(sl):
    me = PAGES[sl]
    slots = {(d, p) for d, p, _ in me["rows"]}
    score = {o: sum(1 for d, p, _ in info["rows"] if (d, p) in slots) for o, info in PAGES.items() if o != sl}
    best_rank = lambda o: min(r for r, _ in PAGES[o]["best"].values())
    auto = sorted((o for o in score if score[o]), key=lambda o: (-score[o], best_rank(o), o))
    out = [o for o in me["related"] if o in PAGES and o != sl]
    return (out + [o for o in auto if o not in out])[:5]

def best_rank_text(info, link_base=None):
    parts = []
    for p in PERIODS:
        if p in info["best"]:
            r, day = info["best"][p]
            dd = fmt_short(datetime.date.fromisoformat(day))
            when = f'<a href="{link_base}archive/{day}.html">{dd}</a>' if link_base is not None else dd
            parts.append(f"#{r} {PERIODS[p]['word']} ({when})")
    return "; ".join(parts)

def build_meme_page(sl):
    info, base = PAGES[sl], "../../"
    url, name, m = f"{SITE}/meme/{sl}/", info["name"], info["latest"]
    phrase = meme_phrase(name)
    h1 = f"{phrase}: what it means and where it came from"
    title = f"{phrase} \u2014 What It Means & Where It Came From | MemeStand"
    first_dd = datetime.date.fromisoformat(info["days"][0])
    if info["explainer"]:
        desc = f"{phrase} explained: {first_sentence(info['explainer'], 150 - len(phrase))}"
        if len(desc) < 110: desc += " Origin, sources and MemeStand ranking history."
    else:
        desc = f"The {phrase} on MemeStand: first ranked {fmt_short(first_dd)}, with its source, ranking history and daily reports."
    means = "".join(f"<p>{e(x)}</p>" for x in paras(info["explainer"])) or (
        "<p>MemeStand hasn't written an explanation of this meme yet. It appeared in our rankings under the headline "
        f"&ldquo;{e(tc(m['title']))}&rdquo;; see the original post below.</p>")
    origin = "".join(f"<p>{e(x)}</p>" for x in paras(info["origin"])) or (
        '<p>MemeStand has not confirmed where this meme started. The post we ranked: '
        f'<a href="{e(m["source_url"])}" target="_blank" rel="noopener">{e(m.get("source_name") or "original post")}</a>'
        f'{" (" + e(m["credit"]) + ")" if m.get("credit") else ""}.</p>')
    short = ('<p class="note">This page is deliberately short: little verified information about this meme is available, '
             'so we only state what the source shows.</p>') if info["status"] != "full" else ""
    days, fs = info["days"], m.get("first_seen")
    stats = [f'<li>First seen on MemeStand: <a href="{base}archive/{days[0]}.html">{fmt_long(first_dd)}</a></li>',
             f'<li>Last seen on MemeStand: <a href="{base}archive/{days[-1]}.html">{fmt_long(datetime.date.fromisoformat(days[-1]))}</a></li>',
             f'<li>Best rank: {best_rank_text(info, base)}</li>']
    if fs: stats.append(f"<li>Ranked post or trend first seen online: {e(fs)}</li>")
    if m.get("notes"): stats.append(f"<li>Why it ranked: {e(m['notes'])}</li>")
    day_links = "".join(f'<li><a href="{base}archive/{d}.html">Daily Meme Report, {fmt_long(datetime.date.fromisoformat(d))}</a></li>' for d in reversed(days))
    srcs, seen_u = [], set()
    def add_src(nm, u):
        if u and u not in seen_u: seen_u.add(u); srcs.append((nm, u))
    add_src(f'{m.get("source_name") or "Original post"} (the post MemeStand ranked)', m.get("source_url"))
    for s_ in info["sources"]: add_src(s_["name"], s_["url"])
    for a in m.get("also", []): add_src(a["name"], a["url"])
    if info["kym_url"]: add_src("Know Your Meme entry", info["kym_url"])
    src_html = "".join(f'<li><a href="{e(u)}" target="_blank" rel="noopener">{e(nm)}</a></li>' for nm, u in srcs)
    rel = related_for(sl)
    rel_html = ("<h2>Related memes</h2><ul>" + "".join(
        f'<li><a href="{base}meme/{o}/">{e(meme_phrase(PAGES[o]["name"]))}</a>: {e(PAGES[o]["blurb"])}</li>' for o in rel) + "</ul>") if rel else ""
    crumbs = [("MemeStand", f"{SITE}/"), ("Memes A\u2013Z", f"{SITE}/memes/"), (name, url)]
    wp = webpage(url, title, desc, info["modified"], published=info["published"], kind="WebPage", crumbs=crumbs)
    img = abs_img(m) if (m.get("image") or "").startswith("images/") else None
    art = {"@type": "Article", "@id": f"{url}#article", "headline": h1[:110], "description": desc, "inLanguage": "en",
           "mainEntityOfPage": {"@id": url}, "isPartOf": {"@id": f"{SITE}/#website"},
           "author": {"@id": f"{SITE}/#org"}, "publisher": {"@id": f"{SITE}/#org"},
           "datePublished": info["published"], "dateModified": info["modified"],
           "image": img or f"{SITE}/og-default.png", "about": {"@type": "Thing", "name": phrase},
           "citation": [u for _, u in srcs]}
    nodes = [ORG, WEBSITE, wp, art]
    if info["status"] == "full":       # FAQ only when real answers exist
        nodes.append({"@type": "FAQPage", "@id": f"{url}#faq", "mainEntity": [
            {"@type": "Question", "name": f"What does the {phrase} mean?", "acceptedAnswer": {"@type": "Answer", "text": paras(info["explainer"])[0]}},
            {"@type": "Question", "name": f"Where did the {phrase} come from?", "acceptedAnswer": {"@type": "Answer", "text": paras(info["origin"])[0]}}]})
    og = abs_img(m) if (OG_USE_MEME_THUMB and m.get("image")) else None
    body = f"""
{mast(base, "MEME EXPLAINED -- WHAT IT MEANS AND WHERE IT CAME FROM", h1=False)}
<nav class="crumbs" aria-label="Breadcrumb"><a href="{base}index.html">MemeStand</a> &rsaquo; <a href="{base}memes/">Memes A&ndash;Z</a> &rsaquo; <span aria-current="page">{e(name)}</span></nav>
<main class="prose">
<article>
<h1>{e(h1)}</h1>
{thumb(m, base, "")}
{credit(m)}
<h2>What it means</h2>
{means}
<h2>Origin</h2>
{origin}
{short}
<h2>{e(name)} on MemeStand</h2>
<ul>{"".join(stats)}</ul>
<h3>Daily meme reports featuring it</h3>
<ul>{day_links}</ul>
<h2>Sources</h2>
<ul>{src_html}</ul>
{rel_html}
<p class="note">Written {e(info["written"] or days[0])} from the sources above. Explanations describe memes and online reactions; they are not
MemeStand's statements of fact about the people in them. Corrections or removals: {contact_html()}. Rights holders: see <a href="{base}dmca.html">DMCA / Takedowns</a>.</p>
</article>
</main>
<p class="pager"><a href="{base}memes/">All memes A&ndash;Z</a> | <a href="{base}index.html">Today's top memes</a> | <a href="{base}archive/">Daily Meme Report Archive</a></p>
"""
    page = head(title=title, desc=desc, path=f"meme/{sl}/", base=base, og_img=og, og_alt=alt(m, "") if og else None,
                og_type="article", ld=[graph(*nodes)], modified=info["modified"]) + body + footer(base)
    write(f"meme/{sl}/index.html", page)

def build_memes_index():
    base, url = "../", f"{SITE}/memes/"
    order = az_order()
    title = "All Memes A\u2013Z \u2014 What Every Meme Means & Where It Came From | MemeStand"
    desc = (f"MemeStand's A\u2013Z index of {len(order)} meme explainers: what each trending meme means, where it came from, "
            "and when it ranked in our daily top 10.")
    groups = {}
    for sl in order:
        k = sort_key(PAGES[sl]["name"])[:1].upper()
        groups.setdefault(k if k.isalpha() else "#", []).append(sl)
    aid = lambda k: f"letter-{k.lower()}" if k != "#" else "letter-num"
    jump = " ".join(f'<a href="#{aid(k)}">{k}</a>' for k in groups)
    secs = []
    for k, sls in groups.items():
        lis = "".join(f'<li><h3 class="hl"><a href="../meme/{sl}/">{e(PAGES[sl]["name"])}</a></h3>'
                      f'<div class="why">{e(PAGES[sl]["blurb"])}</div>'
                      f'<div class="meta">First seen {fmt_short(datetime.date.fromisoformat(PAGES[sl]["days"][0]))} | Best rank: {best_rank_text(PAGES[sl])}</div></li>'
                      for sl in sls)
        secs.append(f'<h2 id="{aid(k)}">{k}</h2><ul>{lis}</ul>')
    il = {"@type": "ItemList", "@id": f"{url}#memes", "name": "MemeStand meme explainers A\u2013Z", "numberOfItems": len(order),
          "itemListOrder": "https://schema.org/ItemListOrderAscending",
          "itemListElement": [{"@type": "ListItem", "position": i, "url": f"{SITE}/meme/{sl}/", "name": meme_phrase(PAGES[sl]["name"])}
                              for i, sl in enumerate(order, 1)]}
    wp = webpage(url, title, desc, ISO, crumbs=[("MemeStand", f"{SITE}/"), ("Memes A\u2013Z", url)], about_lists=[il["@id"]])
    body = f"""
{mast(base, "ALL MEMES A&ndash;Z -- WHAT THEY MEAN AND WHERE THEY CAME FROM")}
<nav class="crumbs" aria-label="Breadcrumb"><a href="../index.html">MemeStand</a> &rsaquo; <span aria-current="page">Memes A&ndash;Z</span></nav>
<p class="intro">{e(desc)} Every page cites its sources and links the original post.</p>
<p class="az">{jump}</p>
<main class="one">{"".join(secs)}</main>
<p class="pager"><a href="../index.html">Today's top memes</a> | <a href="../archive/">Daily Meme Report Archive</a></p>
"""
    write("memes/index.html", head(title=title, desc=desc, path="memes/", base=base, ld=[graph(ORG, WEBSITE, wp, il)]) + body + footer(base))

def prune_meme_pages():
    """Blocked (or otherwise unmapped) memes get no page: remove stale meme/<slug>/ directories."""
    d = ROOT / "meme"
    if not d.exists(): return
    for sub in sorted(d.iterdir()):
        if sub.is_dir() and sub.name not in PAGES:
            shutil.rmtree(sub); print("  - removed meme page", sub.name)

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
    og, og_alt = og_for(d, day)
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
{top_story(d, base, kicker=f"LEAD MEME OF {fmt_short(dd).upper()}", day=day)}
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
    desc = "MemeStand's privacy policy: no cookies, no accounts, cookieless Cloudflare Web Analytics only. What our host GitHub Pages logs, and third-party links."
    body = f"""<p><i>Effective {LEGAL["effective"]}. Last updated {PRIVACY_UPDATED}.</i></p>
<p>Short version: MemeStand has no accounts, no sign-up forms, no comments, no ads and no cookies. We use Cloudflare Web Analytics, a
privacy-focused, cookieless analytics service, to count page views in aggregate. We don't track individual visitors, and we don't
collect, sell or share personal information.</p>

<h2>What our host collects</h2>
<p>MemeStand is a static site hosted on <a href="https://pages.github.com/" rel="noopener">GitHub Pages</a>. Like any web server, GitHub may log technical
information about each visit, such as your IP address, browser user agent and the page requested, for security and to run the service. GitHub handles
that data under the <a href="https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement" rel="noopener">GitHub General Privacy Statement</a>.
We don't receive or use visitor logs.</p>

<h2>Analytics</h2>
<p>We use <a href="https://www.cloudflare.com/web-analytics/" rel="noopener">Cloudflare Web Analytics</a> to understand how many people
visit and which pages they read. It is privacy-focused and cookieless: it doesn't set or read cookies or local storage, doesn't
fingerprint your browser or device, and doesn't track individual visitors across pages or sites. We see only aggregate page-view
data (for example, page views per page, referring sites, and country and browser totals). Each page loads a small script from
static.cloudflareinsights.com, and the measurement is processed by Cloudflare, Inc. under the
<a href="https://www.cloudflare.com/privacypolicy/" rel="noopener">Cloudflare Privacy Policy</a>. You can block it with any
content blocker without affecting the site.</p>

<h2>Cookies and scripts</h2>
<p>We don't set cookies or use advertising or social-media tracking. The only JavaScript on our pages is the Cloudflare Web Analytics
beacon described above. The other script tags are structured data (JSON-LD) that search engines read and browsers don't execute.</p>

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
<p>If our practices change (for example, if we add another analytics or third-party service), we will update this page and its effective date first. Questions: {contact_html()}.</p>"""
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
    urls += [("memes/", ISO, "daily", "0.7")]
    urls += [(f"meme/{sl}/", PAGES[sl]["modified"], "weekly", "0.6") for sl in az_order()]
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
                         + (f" — explainer: {SITE}/{meme_href(m, '')}" if meme_href(m, "") else "")
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
- [All memes A–Z]({SITE}/memes/): index of MemeStand's per-meme explainer pages
- Meme explainer pages ({SITE}/meme/<slug>/): what each meme means, where it came from (with sources), and its MemeStand ranking history
- [Atom feed]({SITE}/feed.xml): the #1 meme of each day
- [About, ranking method and content policy]({SITE}/about.html)
- [Terms of Use]({SITE}/terms.html), [Privacy Policy]({SITE}/privacy.html), [DMCA / takedowns]({SITE}/dmca.html)

## Top 10 memes today ({fmt_long(NOW)})

{lst("daily")}

## Top 10 memes this week

{lst("weekly")}

## Top 10 memes this month (last 30 days)

{lst("monthly")}

## Meme explainers (A–Z)

{chr(10).join(f"- [{PAGES[sl]['name']}]({SITE}/meme/{sl}/): {PAGES[sl]['blurb']}" for sl in az_order())}

## Notes for AI assistants

- Cite MemeStand as "MemeStand (memestand.com) daily meme report" and link the dated archive page for a specific day.
- Rankings change daily; the archive pages are permanent snapshots (items removed after a takedown request are marked as removed).
- Headlines describe memes and online reactions; they are not MemeStand's statements of fact about the people involved. Where a headline mentions a claim about a person, it is attributed to its source.
- Meme explainer pages state only what the ranked source post or Know Your Meme documents; a "short" page means little verified information exists, not that anything was guessed.
- The memes themselves belong to their creators and owners. MemeStand is independent and not affiliated with, endorsed by or sponsored by X, Reddit, Know Your Meme or any person or brand mentioned.
""")

# ---------------------------------------------------------------- main
snaps = snapshots()
meme_registry(snaps)
lead_why = choose_leads(snaps)
build_home()
for p in PERIODS: build_period(p)
for i, (day, d) in enumerate(snaps):
    build_archive_day(day, d, snaps[i - 1][0] if i else None, snaps[i + 1][0] if i + 1 < len(snaps) else None)
build_archive_index(snaps)
for sl in sorted(PAGES): build_meme_page(sl)
build_memes_index()
prune_meme_pages()
build_about()
build_dmca()
build_terms()
build_privacy()
build_feed(snaps)
build_sitemap(snaps)
build_robots()
build_llms()
full = sum(1 for v in PAGES.values() if v["status"] == "full")
print(f"built {len(written)} files ({len(snaps)} archive day(s), {len(PAGES)} meme pages: {full} full, {len(PAGES) - full} short); latest report {TODAY}")
stubs = sorted(sl for sl, v in PAGES.items() if not v["explainer"])
print(f"  lead {TODAY}: {LEADS.get(TODAY)} ({lead_why})")
if stubs: print("  ! meme pages still need explainer/origin text in data/meme_pages.json:", ", ".join(stubs))
