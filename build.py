#!/usr/bin/env python3
"""Render the whole static site from data/memes.json (plain, headline-style news page).   Usage: python3 build.py

Writes (all generated, don't hand-edit):
  index.html                          homepage: lead story (rotates daily, see UPDATE.md "Lead headline") + daily and monthly columns
  top-memes-today/index.html          single-list pages with evidence notes
  trending-memes-this-week/index.html
  best-memes-this-month/index.html
  archive/YYYY-MM-DD.html             one "Daily Meme Report" per day (rendered from data/archive/*.json)
  archive/index.html                  archive index
  about.html                          what MemeStand is + ranking method + content/editorial policy
  terms.html, privacy.html, dmca.html legal pages (text lives in this file; settings in LEGAL below)
  feed.xml                            Atom feed, one entry per daily report
  sitemap.xml, robots.txt, llms.txt   crawler / AI-assistant discovery
  google327e53c932d0bf40.html         Google Search Console URL-prefix verification (exact one-line body;
                                      rewritten every build, not a page, not in the sitemap)
  meme/<slug>/index.html              one permanent explainer page per meme (text from data/meme_pages.json;
                                      a page stays up after the meme leaves the ranked lists)
  memes/index.html                    A-Z index of every meme page
  meme-index/index.html               lifecycle index: rising, peaking, fading, from archive scores
  embed/index.html                    how to embed the top-5 widget
  embed/top5.html                     small iframe page, top 5 memes today, links back here

data/meme_pages.json is the persistent explainer store keyed by slug: text is written once (by the daily routine,
see UPDATE.md "Meme pages") and reused forever. The build adds a stub entry for any new meme id and never rewrites text.

Each run snapshots data/memes.json to data/archive/<PT date>.json (overwriting only today's
snapshot), and never deletes older snapshots or archive pages, so past days survive rebuilds.
The build is deterministic: re-running with the same data produces identical files.

Daily top-10 rows can show a short history note (New today, First time, rank movement since
yesterday, N days at #1). tools/rank_history.py derives that only from archived daily lists
and the meme-page slug. Weekly and monthly lists, the lead headline, and the score are unchanged.

Takedowns: items matching data/blocklist.json are replaced by a removal notice on every page (archives
included), scrubbed from data/archive/*.json, and their local thumbnails deleted (see tools/legal.py).
Blocked memes also lose their meme page and their entry in data/meme_pages.json.
"""
import json, html, datetime, pathlib, re, shutil, sys, hashlib, base64
from zoneinfo import ZoneInfo
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "tools"))
from legal import load_blocklist, blocked_by, exclusion_reason
from rank_history import daily_ranks, history_notes, meme_identity
from post_cards import file_for as post_card_file, displayed_as_post_card
from safe_url import safe_url
import momentum

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
PRIVACY_UPDATED = "November 4, 2026"   # bump when the privacy policy text changes

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

# Hashed into the Content-Security-Policy. Keep this the exact script tag upd_html() emits.
UPD_SCRIPT = (
    "<script>(function(){var t=document.getElementById('upd-time');if(!t)return;"
    "var iso=t.getAttribute('datetime');if(!iso)return;var d=new Date(iso);if(isNaN(d))return;"
    "function plural(n,u){return n+' '+u+(n===1?'':'S');}"
    "function tick(){var s=Math.max(0,Math.floor((Date.now()-d.getTime())/1000));"
    "var m=Math.floor(s/60),h=Math.floor(m/60),dy=Math.floor(h/24);"
    "t.textContent=dy>=1?plural(dy,'DAY')+' AGO':h>=1?plural(h,'HOUR')+' AGO':"
    "m>=1?plural(m,'MIN')+' AGO':'JUST NOW';}"
    "tick();setInterval(tick,30000);})();</script>"
)

def upd_html():
    """Drudge-style UPDATED line: absolute stamp in <time datetime>, plus a tiny first-party
    script that rewrites the visible text to a relative 'X MIN/HOURS/DAYS AGO' in the visitor's
    browser. Falls back to the absolute PT stamp if JS is off."""
    absolute = NOW.strftime("%a %b %-d, %Y %-I:%M %p PT").upper()
    return (
        (f'<div class="upd">UPDATED <time id="upd-time" datetime="{ISO}">{absolute}</time></div>' + chr(10))
        + UPD_SCRIPT
    )


def _tc_plain(w, i):
    core = re.sub(r"^[^\w]+|[^\w']+$", "", w)
    if core.upper() in SPECIAL: return w.replace(core, SPECIAL[core.upper()])
    if core.upper().endswith("'S") and core.upper()[:-2] in ACRONYMS: return w[:-1] + "s"
    if core.upper() in ACRONYMS or re.search(r"\d", core): return w
    lw = w.lower()
    if i and core.lower() in SMALL: return lw
    return re.sub(r"[a-z]", lambda m: m.group().upper(), lw, count=1)

def _tc_word(w, i):
    """Keep an acronym at the start of a hyphenated word: AI-GENERATED -> AI-Generated."""
    bits = w.split("-")
    if len(bits) > 1:
        cores = [re.sub(r"^[^\w]+|[^\w']+$", "", b).upper() for b in bits]
        if any(c in ACRONYMS or c in SPECIAL for c in cores):
            return "-".join(_tc_plain(b, i if n == 0 else 1) for n, b in enumerate(bits))
    return _tc_plain(w, i)

def tc(s):
    """Headline in ALL CAPS -> readable Title Case for titles/descriptions/alt text."""
    return " ".join(_tc_word(w, i) for i, w in enumerate((s or "").split()))

def display_title(s):
    """Sensible casing for a stored headline. A line that is already written in sentence
    case is left alone, so a mixed-case quotation is not recased. A few lowercase letters
    inside a token like 2000s do not keep the rest of an ALL CAPS headline shouting."""
    s = str(s or "")
    if not s or s == REMOVED:
        return s
    letters = [c for c in s if c.isalpha()]
    if letters and sum(c.islower() for c in letters) / len(letters) >= 0.2:
        return s
    return tc(s)

def uses_post_card(m):
    """True when the picture is an approved attributed post card, not a photo or a hotlink.
    Stays true after rank.py writes the card path onto the row."""
    return displayed_as_post_card(m.get("image"), m.get("image_url"), m.get("image_kind"), m.get("id"))

def img_src(m):
    native = m.get("image") or m.get("image_url")
    if native:
        return native
    return post_card_file(m.get("id"))

_DIMS = {}
def img_dims(src):
    """(width, height) of a local image file, read with PIL at build time; None for hotlinks / missing files.
    Every <img> gets these as width/height attributes so the browser reserves its space before it loads (no layout shift)."""
    if not src or src.startswith("http"): return None
    if src not in _DIMS:
        try:
            from PIL import Image
            with Image.open(ROOT / src) as im: _DIMS[src] = im.size
        except Exception:
            _DIMS[src] = None
    return _DIMS[src]

def wh_attrs(src):
    d = img_dims(src)
    return f' width="{d[0]}" height="{d[1]}"' if d else ' width="400" height="300" style="aspect-ratio:4/3;object-fit:contain"'
def abs_img(m):
    s = img_src(m)
    if not s: return None
    return s if s.startswith("http") else f"{SITE}/{s}"

PERIODS = {
    "daily":   {"h2": "TOP 10 MEMES TODAY",      "slug": "top-memes-today",          "word": "today"},
    "weekly":  {"h2": "TOP 10 MEMES THIS WEEK",  "slug": "trending-memes-this-week", "word": "this week"},
    "monthly": {"h2": "TOP 10 MEMES THIS MONTH", "slug": "best-memes-this-month",    "word": "this month"},
}
# Homepage columns only. Weekly is a supported list in the header, footer, and period pager.
MAIN_PERIODS = ("daily", "monthly")

THEME_HEAD = ('<meta name="color-scheme" content="light dark">'
    '<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">'
    '<meta name="theme-color" content="#121212" media="(prefers-color-scheme: dark)">'
    "<script>try{var t=localStorage.getItem('theme');if(t==='dark'||t==='light'){document.documentElement.setAttribute('data-theme',t);"
    "document.querySelectorAll('meta[name=theme-color]').forEach(function(m){m.content=t==='dark'?'#121212':'#ffffff'});}}catch(e){}</script>")
# Theme toggle: fixed 34px button, absolutely positioned in the masthead (no layout shift); choice saved in localStorage.
THEME_TOGGLE = ('<button class="tt" type="button" aria-label="Toggle dark mode" title="Toggle dark mode"></button>'
    "<script>(function(){var b=document.querySelector('.tt'),r=document.documentElement;if(!b)return;"
    "b.addEventListener('click',function(){var c=r.getAttribute('data-theme')||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');"
    "var n=c==='dark'?'light':'dark';r.setAttribute('data-theme',n);try{localStorage.setItem('theme',n)}catch(e){}"
    "document.querySelectorAll('meta[name=theme-color]').forEach(function(m){m.content=n==='dark'?'#121212':'#ffffff'});});})();</script>")

CSS = """
 :root{--bg:#fff;--fg:#000;--fg2:#222;--muted:#444;--line:#bbb;--hair:#e0e0e0;--rule:#000;--card:#fff;--thumb:#f3f3f3;--bar:#000;--barfg:#fff;--red:#c00;--redbg:#c00;--link:#00c;--green:#080;--read:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Liberation Serif","Noto Serif","Times New Roman",serif;color-scheme:light}
 @media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#121212;--fg:#ececec;--fg2:#d6d6d6;--muted:#b4b4b4;--line:#444;--hair:#3a3a3a;--rule:#8a8a8a;--card:#1c1c1c;--thumb:#262626;--bar:#2a2a2a;--barfg:#fff;--red:#ff5c5c;--redbg:#c00;--link:#8fb4ff;--green:#3fb950;color-scheme:dark}}
 :root[data-theme=dark]{--bg:#121212;--fg:#ececec;--fg2:#d6d6d6;--muted:#b4b4b4;--line:#444;--hair:#3a3a3a;--rule:#8a8a8a;--card:#1c1c1c;--thumb:#262626;--bar:#2a2a2a;--barfg:#fff;--red:#ff5c5c;--redbg:#c00;--link:#8fb4ff;--green:#3fb950;color-scheme:dark}
 .tt{position:absolute;top:4px;right:0;width:34px;height:34px;padding:0;margin:0;border:1px solid var(--line);border-radius:50%;background:var(--card);color:var(--fg);font:18px/32px sans-serif;text-align:center;cursor:pointer}
 .tt::before{content:"\\263E"} :root[data-theme=dark] .tt::before{content:"\\2600"}
 @media(prefers-color-scheme:dark){:root:not([data-theme=light]) .tt::before{content:"\\2600"}}
 .tt:focus-visible{outline:2px solid var(--link);outline-offset:2px}
 *,*::before,*::after{box-sizing:border-box}
 html{-webkit-text-size-adjust:100%;text-size-adjust:100%}
 body{background:var(--bg);color:var(--fg);font-family:"Courier New",Courier,monospace;margin:0 auto;max-width:1180px;padding:10px 16px 40px;overflow-wrap:break-word}
 img{max-width:100%;height:auto}
 a{color:var(--fg);text-decoration:none} a:hover{text-decoration:underline}
 .mast{position:relative;text-align:center;border-bottom:3px double var(--rule);padding-bottom:8px}
 .mast h1{margin:0;font-weight:normal;font-size:inherit}
 .mast .logo{display:block;font-size:52px;letter-spacing:3px;margin-top:6px}
 .mast .logo a{display:inline-flex;align-items:center;justify-content:center;gap:10px;color:var(--fg);text-decoration:none}
 .mast .logo .mark{width:.78em;height:.78em;flex:none;display:block}
 .mast .word{border-bottom:3px solid var(--redbg);line-height:.9}
 .mast .tag{display:block;font-size:13px;letter-spacing:2px;font-weight:normal}
 .mast .periods{margin:8px 0 0;font-size:12px;letter-spacing:0} .mast .periods a{color:var(--link);margin:0 6px;text-decoration:underline}
 .intro{text-align:center;font-size:12px;margin:6px auto 0;max-width:820px;color:var(--muted)} .intro a{color:var(--link);text-decoration:underline}
 .upd{text-align:center;font-size:12px;margin:6px 0 2px}
 .top{text-align:center;margin:18px auto 30px;max-width:900px;padding-bottom:22px;border-bottom:3px double var(--rule)}
 .top img{box-sizing:content-box;max-width:calc(100% - 2px);max-height:520px;border:1px solid var(--rule);object-fit:contain}
 .top .card{min-height:240px;font-size:28px}
 .top h2{margin:10px 0 0;text-decoration:none}
 .top .hl a{color:var(--red);font-size:26px;font-weight:650;line-height:1.3}
 .top .hl.clip a,.hl.clip a{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
 .top .kick{display:block;font-size:13px;letter-spacing:2px;color:var(--red);margin-bottom:4px}
 .top .meta{margin-top:6px}
 .grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0;margin-top:10px}
 .grid.two{grid-template-columns:repeat(2,minmax(0,1fr))}
 .grid .col{padding:0 20px;min-width:0} .grid .col:first-child{padding-left:0} .grid .col:last-child{padding-right:0}
 .grid .col+.col{border-left:2px solid var(--rule)}
 .one{max-width:640px;margin:10px auto 0}
 .col{margin-bottom:10px}
 .col>h2{position:sticky;top:0;z-index:5;margin:0 0 16px;padding:11px 12px;background:var(--bar);color:var(--barfg);font-size:18px;line-height:1.2;
   letter-spacing:2px;text-transform:uppercase;text-align:center;text-decoration:none;border-bottom:5px solid var(--redbg)}
 #weekly>h2{border-bottom-color:var(--link)} #monthly>h2{border-bottom-color:var(--green)}
 .col>h2 a{color:var(--barfg);display:block} .col>h2 a::after{content:" \\203A"}
 h2{font-size:20px;text-align:center;text-decoration:underline;margin:6px 0 12px} h2 a{color:var(--fg)}
 h3{margin:0;font-size:inherit}
 ul{list-style:none;padding:0;margin:0}
 li{margin:0 0 22px;padding:12px;border:1px solid var(--line);border-top:3px solid var(--rule);background:var(--card);box-shadow:0 2px 4px rgba(0,0,0,.10)}
 .thumb{display:block;width:100%;max-height:260px;object-fit:contain;background:var(--thumb);border:1px solid var(--line);margin-bottom:10px}
 .thumb.postcard{width:100%;height:auto;max-height:none;object-fit:contain;background:var(--card)}
 .top img.postcard{width:100%;height:auto;max-height:640px;object-fit:contain;background:var(--card)}
 .one .thumb{max-height:420px}
 .card{display:flex;align-items:center;justify-content:center;text-align:center;min-height:120px;padding:14px;border:2px solid var(--rule);font-weight:bold;font-size:17px;background:var(--card)}
 .hl{font-size:18px;font-weight:650;line-height:1.35}
 .textmeme{text-transform:none}
 .textmeme .card{text-transform:none;font-size:17px;line-height:1.35}
 .top .textmeme .card{font-size:26px;line-height:1.25;min-height:140px}
 .sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
 li .zone-lead{display:grid;grid-template-columns:3.15rem minmax(0,1fr);column-gap:1rem;align-items:start}
 li .zone-lead>.rk{margin:0;padding:0;background:none;color:var(--red);font-family:var(--read);font-size:2.55rem;font-weight:650;line-height:.82;letter-spacing:-.03em;font-variant-numeric:lining-nums tabular-nums;text-align:right;white-space:nowrap}
 li .lead-copy{min-width:0}
 .meta{font-size:11px;margin-top:6px;color:var(--muted)} .src{color:var(--link);margin-right:8px} .fs{color:var(--muted)}
 .mv{display:flex;flex-wrap:wrap;column-gap:10px;row-gap:2px;align-items:baseline;margin:4px 0 0;font-size:11px;line-height:1.35;letter-spacing:.02em;color:var(--muted)}
 .mv span{white-space:nowrap} .mv-up{color:var(--green)} .mv-down{color:var(--red)} .mv-new,.mv-first{color:var(--fg2)}
 .credit{font-size:11px;margin-top:4px;color:var(--muted)} .credit a{color:var(--link);text-decoration:underline}
 .skip{position:absolute;left:-9999px;top:0} .skip:focus{left:8px;top:8px;background:var(--card);color:var(--link);padding:6px;border:2px solid var(--link);z-index:9}
 a:focus-visible{outline:2px solid var(--link);outline-offset:2px}
 .why{font-size:12px;margin-top:6px;color:var(--fg2)}
 .more{text-align:center;font-size:12px;margin:14px 0 0} .more a{color:var(--link)}
 .pager{text-align:center;font-size:13px;margin:14px 0} .pager a{color:var(--link);margin:0 10px}
 .prose{max-width:760px;margin:16px auto;font-size:14px;line-height:1.5} .prose a{color:var(--link);text-decoration:underline} .prose h2{text-align:left;text-decoration:none;margin-top:28px;padding:7px 10px;background:var(--bar);color:var(--barfg);font-size:17px;letter-spacing:1px} .prose li{border:0;margin:0 0 6px;padding:0;list-style:disc;box-shadow:none;background:none} .prose ul,.prose ol{padding-left:22px} .prose td,.prose th{border:1px solid var(--line);padding:3px 6px;font-size:12px} .prose table{border-collapse:collapse;max-width:100%}
 nav.foot{margin-bottom:6px;font-size:12px} nav.foot a{color:var(--link);margin:0 6px;text-decoration:underline} footer p{margin:6px auto;max-width:860px}
 .crumbs{font-size:12px;margin:10px auto 0;max-width:760px} .crumbs a{color:var(--link);text-decoration:underline}
 .prose h1{font-size:24px;line-height:1.25;margin:10px 0 12px} .prose h3{margin:14px 0 6px} .prose .thumb{max-height:420px;max-width:400px} .prose .thumb.postcard{max-width:520px;max-height:none} .prose .card{max-width:400px}
 .copy{font-family:var(--read);min-width:0;color:var(--fg)}
 .copy .hl,.copy .dek,.copy .credit,.copy .meta,.copy .go,.copy .fold{font-family:var(--read)}
 .copy .hl a{color:var(--fg);overflow-wrap:break-word}
 .dek{margin:8px 0 0;max-width:62ch;font-size:17px;line-height:1.55;color:var(--fg2)}
 .copy .zone+.zone{margin-top:12px;padding-top:11px;border-top:1px solid var(--hair)}
 .copy .mv{margin:0;font-size:13px;line-height:1.45;letter-spacing:0;font-weight:400;color:var(--muted)}
 .copy .mv span+span::before{content:"\\00b7";margin-right:8px;color:var(--muted)}
 .copy .credit{margin:0;font-size:15px;line-height:1.5;color:var(--fg2)}
 .copy .rights{color:var(--muted)}
 .copy .go{margin:2px 0 0;font-size:15px;line-height:1.4}
 .copy .go a{color:var(--link);font-weight:650;text-decoration:underline;text-underline-offset:2px}
 .copy .meta{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 12px;margin:0;font-size:14px;line-height:1.45}
 .copy .src{color:var(--link);margin:0;min-width:0;max-width:100%;text-decoration:underline;text-underline-offset:2px;overflow-wrap:anywhere}
 .fold{margin:0;min-width:0;max-width:100%}
 .explainer .zone-more{margin-top:22px;padding-top:14px;border-top:1px solid var(--hair)}
 .fold summary{cursor:pointer;color:var(--link);font-size:15px;line-height:1.4;width:fit-content;max-width:100%;overflow-wrap:anywhere;list-style:none}
 .fold summary::-webkit-details-marker{display:none}
 .fold summary::before{content:"\\25B8\\00a0"}
 .fold[open] summary::before{content:"\\25BE\\00a0"}
 .fold summary:focus-visible{outline:2px solid var(--link);outline-offset:3px}
 .foldbody{margin-top:8px;color:var(--fg2);font-size:15px;line-height:1.55;overflow-wrap:anywhere}
 .foldbody p{margin:0 0 8px}
 .srcrow{display:flex;flex-wrap:wrap;gap:6px 14px;min-width:0}
 .top .copy{text-align:center}
 .top .copy .hl a{color:var(--red)}
 .top .dek{margin-left:auto;margin-right:auto}
 .top .copy .meta{justify-content:center}
 .top .copy .fold summary{margin-left:auto;margin-right:auto}
 .top .kick{font-family:"Courier New",Courier,monospace}
 .explainer{font-family:var(--read);font-size:18px;line-height:1.65}
 .explainer h1,.explainer h2,.explainer h3,.explainer p,.explainer li{font-family:var(--read)}
 .explainer h1{font-size:1.75rem;line-height:1.28;font-weight:650}
 .explainer h2{background:none;color:var(--fg);letter-spacing:0;text-align:left;text-decoration:none;margin:1.35em 0 .4em;padding:0;font-size:1.28rem;font-weight:650;line-height:1.3}
 .explainer h3{font-size:1.05rem;font-weight:650;color:var(--fg2);letter-spacing:0}
 .prose .note{font-size:12px;color:var(--muted)} .az{text-align:center;font-size:14px;margin:8px 0} .az a{color:var(--link);margin:0 4px;text-decoration:underline}
 .one h2[id]{position:sticky;top:0;z-index:5;text-align:left;text-decoration:none;margin:28px 0 14px;padding:8px 12px;background:var(--bar);color:var(--barfg);border-bottom:5px solid var(--redbg)}
 .prose .life,.life{list-style:none;padding-left:0}
 .life li{display:grid;grid-template-columns:5.4rem minmax(0,1fr);column-gap:.8rem;align-items:center}
 .prose .life li{border:1px solid var(--line);border-top:3px solid var(--rule);margin:0 0 12px;padding:10px;list-style:none;box-shadow:0 2px 4px rgba(0,0,0,.10);background:var(--card)}
 .life .who{font-family:var(--read);font-size:18px;font-weight:650;line-height:1.3} .life .who a{color:var(--fg)}
 .life .sub{font-size:12px;color:var(--muted);margin-top:3px;line-height:1.4}
 .life .st{font-size:11px;letter-spacing:.08em;text-transform:uppercase;font-weight:650}
 .st-rising{color:var(--green)} .st-fading{color:var(--red)} .st-peaking{color:var(--fg)} .st-new{color:var(--link)}
 .spark{display:block;color:inherit} .delta{font-family:var(--read);font-size:1.65rem;font-weight:650;line-height:.85;text-align:right;font-variant-numeric:tabular-nums}
 .delta.up{color:var(--green)} .delta.down{color:var(--red)}
 .method{font-size:13px;line-height:1.5;text-align:left}
 .embed-wrap{max-width:420px;margin:0 auto}
 .embed-brand{display:flex;align-items:center;justify-content:center;gap:8px;font-size:22px;letter-spacing:2px;border-bottom:3px double var(--rule);padding:2px 8px 6px}
 .embed-brand img{width:22px;height:22px;flex:none;display:block}
 .embed-brand a{display:inline-flex;align-items:center;gap:8px;color:var(--fg);text-decoration:none}
 .embed-brand .word{border-bottom:3px solid var(--redbg);line-height:.9}
 .embed-wrap h1{font-family:"Courier New",Courier,monospace;font-size:13px;letter-spacing:1px;font-weight:normal;text-align:center;margin:8px 0 10px}
 .embed-list li{display:grid;grid-template-columns:2.4rem minmax(0,1fr);column-gap:.6rem;align-items:start;margin:0 0 8px;padding:8px 8px 8px 4px}
 .embed-list .rk{margin:0;padding:0;background:none;color:var(--red);font-family:var(--read);font-size:1.85rem;font-weight:650;line-height:.82;letter-spacing:-.03em;font-variant-numeric:lining-nums tabular-nums;text-align:right}
 .embed-list .name{font-family:var(--read);font-size:16px;font-weight:650;line-height:1.3;color:var(--fg)}
 .embed-foot{text-align:center;font-size:12px;margin:8px 0 0} .embed-foot a{color:var(--link);text-decoration:underline}
 .snippet{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;line-height:1.45;border:1px solid var(--line);padding:10px;background:var(--thumb);text-align:left}
 footer{border-top:3px double var(--rule);margin-top:28px;padding-top:10px;font-size:11px;text-align:center;color:var(--muted)}
 @media(max-width:860px){
  body{padding:8px 14px 32px}
  .mast .logo{font-size:32px;letter-spacing:1px} .mast .logo a{gap:6px} .mast .tag{font-size:12px;letter-spacing:1px}
  .intro{font-size:13px;line-height:1.4}
  .top{margin:14px auto 26px;padding-bottom:20px}
  .top img{max-height:60vh}
  .top .card{min-height:0;font-size:20px;padding:18px 14px}
  .top .hl a{font-size:24px;line-height:1.3}
  .top .textmeme .card{font-size:22px;min-height:0}
  .grid{display:block;margin-top:0}
  .grid .col,.grid .col:first-child,.grid .col:last-child{padding:0}
  .grid .col+.col{border-left:0;margin-top:40px;padding-top:14px;border-top:3px double var(--rule)}
  .col>h2{font-size:18px;padding:13px 10px;margin:0 0 16px} .col>h2 a{margin:-13px -10px;padding:13px 10px}
  footer p a,.prose p a,.prose .note a{padding:16px 0}
  .prose a{overflow-wrap:anywhere}
  li{margin:0 0 26px;padding:12px}
  .thumb,.one .thumb{max-height:380px}
  .card{font-size:17px}
  .hl,.copy .hl{font-size:19px;line-height:1.35}
  .dek{font-size:17px}
  .copy .credit,.foldbody,.copy .meta{font-size:16px;line-height:1.5}
  .copy .mv{font-size:13px}
  .srcrow{flex-direction:row;flex-wrap:wrap;align-items:center}
  .why{font-size:16px;line-height:1.5}
  .hl a{display:inline}
  .hl a.card{display:flex}
  li h3.hl{min-height:44px}
  li .zone-lead{column-gap:.75rem}
  li .zone-lead>.rk{font-size:2.4rem}
  .copy .meta{flex-direction:row;flex-wrap:wrap;align-items:center;column-gap:12px;row-gap:0}
  .copy .go a{display:inline-flex;align-items:center;min-height:44px}
  .copy .zone-src .src{display:inline;min-height:0;padding:2px 0}
  .fold summary{display:inline-flex;align-items:center;min-height:44px;padding:8px 0}
  .top .copy .meta{align-items:center}
  .pager a,.more a,.crumbs a,.az a,nav.foot a,.mast .periods a{display:inline-block;min-height:44px;line-height:44px;padding:0 4px}
  nav.foot{font-size:13px;line-height:1.2} footer{font-size:12px}
  .prose{font-size:16px} .explainer{font-size:18px} .prose h1{font-size:22px} .prose .thumb,.prose .card{max-width:100%}
  .life li{grid-template-columns:4.6rem minmax(0,1fr);column-gap:.65rem}
  .life .who{font-size:17px} .embed-brand{font-size:18px;letter-spacing:1px}
  .prose li{margin-bottom:10px} .prose li a{display:inline-block;padding:10px 0}
 }
"""

# ---------------------------------------------------------------- page chrome
_SCRIPT_TAG = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.I | re.S)
_JS_TYPES = {"text/javascript", "application/javascript", "text/ecmascript", "application/ecmascript", "module"}

def executable_inline_bodies(html):
    """Bodies of inline classic/module scripts. External scripts and JSON-LD are skipped.
    ld+json is not executed, so it is not hashed into script-src."""
    bodies = []
    for attrs, body in _SCRIPT_TAG.findall(html or ""):
        if re.search(r"\bsrc\s*=", attrs, re.I):
            continue
        kind = re.search(r"\btype\s*=\s*['\"]?([^'\"\s>]+)", attrs, re.I)
        if kind and kind.group(1).lower() not in _JS_TYPES:
            continue
        bodies.append(body)
    return bodies

def script_hash(body):
    digest = hashlib.sha256(body.encode("utf-8")).digest()
    return "sha256-" + base64.b64encode(digest).decode("ascii")

def content_security_policy():
    """CSP for the meta tag. Hashes come from the inline scripts this file actually emits.
    frame-ancestors is not honored in a meta policy, so it is left out.
    'unsafe-inline' is required for the <style> block and for the hotlink aspect-ratio style attribute."""
    hashes = []
    for chunk in (THEME_HEAD, THEME_TOGGLE, UPD_SCRIPT):
        for body in executable_inline_bodies(chunk):
            token = script_hash(body)
            if token not in hashes:
                hashes.append(token)
    script = " ".join(["'self'", "https://static.cloudflareinsights.com", *(f"'{h}'" for h in hashes)])
    return (
        "default-src 'self'; "
        f"script-src {script}; "
        "connect-src 'self' https://cloudflareinsights.com; "
        "img-src 'self' https: data:; "
        "media-src 'self' https:; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self' https: data:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )

def head(*, title, desc, path, base, og_img=None, og_alt=None, og_type="website", ld=(), modified=None):
    url = f"{SITE}/{path}"
    og_img = og_img or f"{SITE}/og-default.png"
    og_alt = og_alt or "MemeStand: top 10 memes today, this week and this month"
    lds = "\n".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")}</script>' for x in ld)
    mod = f'\n<meta property="article:modified_time" content="{e(modified)}">' if modified and og_type == "article" else ""
    csp = content_security_policy()
    return f'''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="strict-origin-when-cross-origin">
<meta http-equiv="Content-Security-Policy" content="{csp}">
{THEME_HEAD}
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

def period_nav(base):
    """Header links for the three ranked lists, plus the meme index. Weekly is one of them."""
    labels = (("daily", "Top Memes Today"), ("weekly", "Trending This Week"), ("monthly", "Best of the Month"))
    inner = " | ".join(f'<a href="{base}{PERIODS[k]["slug"]}/">{label}</a>' for k, label in labels)
    inner += f' | <a href="{base}meme-index/">Meme Index</a>'
    return f'<nav class="periods" aria-label="Rankings">{inner}</nav>'

def logo_html(base):
    """Wordmark with the same boxed M as the favicon. The image is decorative; the word is the name."""
    return (f'<span class="logo"><a href="{home_href(base)}">'
            f'<img class="mark" src="{base}favicon.svg" alt="" width="64" height="64">'
            f'<span class="word">MEMESTAND</span></a></span>')

def mast(base, tag, h1=True):
    """Logo stays outside the h1. List pages then expose only the headline as the heading."""
    headline = f'<h1 class="tag">{tag}</h1>' if h1 else f'<span class="tag">{tag}</span>'
    return f'<header class="mast">{logo_html(base)}{headline}{period_nav(base)}{THEME_TOGGLE}</header><div id="content"></div>'

INTRO = "Ranked by cross-platform virality on X, TikTok, Instagram, Reddit, YouTube and Know Your Meme."

def copyright_years():
    return f"{COPY_START}" if NOW.year <= COPY_START else f"{COPY_START}&ndash;{NOW.year}"

def footer(base):
    links = [(home_href(base), "Home"), (f"{base}top-memes-today/", "Top Memes Today"),
             (f"{base}trending-memes-this-week/", "Trending This Week"),
             (f"{base}best-memes-this-month/", "Best of the Month"), (f"{base}meme-index/", "Meme Index"),
             (f"{base}archive/", "Daily Meme Report Archive"),
             (f"{base}memes/", "Memes A&ndash;Z"), (f"{base}embed/", "Embed"),
             (f"{base}feed.xml", "RSS/Atom Feed"), (f"{base}llms.txt", "llms.txt")]
    legal = [(f"{base}about.html", "About &amp; Content Policy"), (f"{base}terms.html", "Terms of Use"),
             (f"{base}privacy.html", "Privacy"), (f"{base}dmca.html", "DMCA / Takedowns")]
    nav = " | ".join(f'<a href="{u}">{t}</a>' for u, t in links)
    nav2 = " | ".join(f'<a href="{u}">{t}</a>' for u, t in legal)
    return f'''<footer><nav class="foot" aria-label="Site">{nav}</nav>
<nav class="foot" aria-label="Legal">{nav2}</nav>
<p>Ranked by cross-platform virality: X engagement and trending stories, TikTok and Instagram post counts, Reddit top feeds, YouTube views and Know Your Meme.
Headlines describe memes and online reactions, not verified facts about the people in them.</p>
<p>All memes and images are &copy; their respective owners and are shown as small, credited thumbnails that link to the original source,
for ranking and commentary. MemeStand is independent and is not affiliated with, endorsed by or sponsored by X, TikTok, Instagram, Reddit, YouTube or Know Your Meme;
their names are used only to identify sources. Rights holders: see <a href="{base}dmca.html">DMCA / Takedowns</a>.</p>
<p>&copy; {copyright_years()} MemeStand. Site design, rankings and compilation only; memes &copy; their respective owners.</p></footer>
{CF_ANALYTICS}
</body></html>
'''

# ---------------------------------------------------------------- items
def alt(m, label):
    a = f"{tc(m['title'])} meme"
    if uses_post_card(m):
        a += ". Attributed post card of the original post, not a screenshot"
    return f"{a} - #{m['rank']} {label} on MemeStand" if label else a

def joke_text(m):
    """The words on a text-only post. Not a generated stand-in for a missing picture."""
    return m.get("card_text") or m["title"]

def text_face(m, base, cls="card"):
    """One text block for a post that has no real image. Links to the meme page; View original stays in the credit."""
    inner = e(joke_text(m))
    h = meme_href(m, base)
    if h: return f'<a class="{cls}" href="{e(h)}">{inner}</a>'
    ok = safe_url(outbound(m), context="text card")
    if not ok:
        return f'<a class="{cls}" href="#">{inner}</a>'
    return f'<a class="{cls}" href="{e(ok)}" target="_blank" rel="noopener">{inner}</a>'

def thumb(m, base, label, cls="thumb", eager=False):
    if m.get("removed"): return ""
    raw = img_src(m)
    if not raw: return ""
    ok_src = safe_url(raw, context="image")
    if not ok_src: return ""
    ext = ok_src.lower().startswith("https://")
    src = ok_src if ext else base + ok_src
    load = 'fetchpriority="high"' if eager else 'loading="lazy"'
    ref = ' referrerpolicy="no-referrer"' if ext else ""
    wh = wh_attrs(raw)   # explicit size (or a fixed 4:3 box for hotlinks) reserves space: no layout shift
    kind = " postcard" if uses_post_card(m) else ""
    href = safe_url(outbound(m), context="thumbnail")
    if href:
        open_a = f'<a href="{e(href)}" target="_blank" rel="noopener">'
    else:
        open_a = '<a href="#">'
    return f'{open_a}<img class="{cls}{kind}" src="{e(src)}" alt="{e(alt(m, label))}"{wh} {load}{ref}></a>'

def load_candidate_rows():
    """Evidence counts and the post text stored with each candidate. Explainer prose is not loaded.
    A slim display row is kept so a written explainer can still render after it leaves the lists."""
    try:
        doc = json.loads((ROOT / "data" / "candidates.json").read_text())
    except Exception:
        return {}, {}, {}
    ev, cards, display = {}, {}, {}
    keep = ("title", "image", "image_url", "image_kind", "source_url", "source_name", "credit",
            "card_text", "also", "first_seen", "notes", "sources")
    for c in doc.get("candidates", []):
        if not c.get("id"):
            continue
        ev[c["id"]] = c.get("ev") or {}
        cards[c["id"]] = {"card_text": c.get("card_text") or "", "source_url": c.get("source_url") or ""}
        display[c["id"]] = {k: c.get(k) for k in keep}
    return ev, cards, display

def load_post_cards():
    try:
        return json.loads((ROOT / "data" / "post_cards.json").read_text()).get("cards") or {}
    except Exception:
        return {}

EVIDENCE, CANDIDATE_CARDS, CANDIDATE_DISPLAY = load_candidate_rows()
POST_CARDS = load_post_cards()
_DIRECT_POST = re.compile(
    r"^https?://(?:www\.)?("
    r"tiktok\.com/@[^/]+/video/\d+"
    r"|instagram\.com/(?:p|reel)/[^/?#]+"
    r"|instagram\.com/[^/]+/reel/[^/?#]+"
    r"|x\.com/(?!i/)[^/]+/status/\d+"
    r"|twitter\.com/(?!i/)[^/]+/status/\d+"
    r"|reddit\.com/r/[^/]+/comments/\w+"
    r"|(?:youtube\.com/watch\?|youtu\.be/)[^?\s]+"
    r")", re.I)

def is_kym_url(url):
    return "knowyourmeme.com" in (url or "").lower()

def is_direct_post(url):
    return bool(url) and not is_kym_url(url) and bool(_DIRECT_POST.match(url.strip()))

def home_href(base):
    """Relative site root. Resolves to the canonical directory URL, not /index.html."""
    return base or "./"

def _handle_token(blob, handle):
    if not blob or not handle:
        return False
    return re.search(rf"(?<![A-Za-z0-9._])@?{re.escape(handle)}(?![A-Za-z0-9._])", blob, re.I) is not None

def credit_handles(credit):
    text = credit or ""
    at = re.search(r"@([A-Za-z0-9._]+)", text)
    user = re.search(r"\bu/([A-Za-z0-9_-]+)", text)
    return (at.group(1) if at else None), (user.group(1) if user else None)

def page_of(m):
    sl = SLUG.get((m or {}).get("id"))
    return PAGES.get(sl) if sl else None

def _creator_candidates(m, page, ev):
    found = []
    for key in ("tiktok", "instagram", "x", "youtube", "reddit"):
        block = (ev or {}).get(key) or {}
        url = block.get("url")
        if is_direct_post(url):
            found.append((url, " ".join(x for x in (block.get("author"), block.get("channel"), url) if x)))
    for a in (m or {}).get("also") or []:
        if is_direct_post(a.get("url")):
            found.append((a["url"], f"{a.get('name') or ''} {a['url']}"))
    for s_ in (page or {}).get("sources") or []:
        if is_direct_post(s_.get("url")):
            found.append((s_["url"], f"{s_.get('name') or ''} {s_['url']}"))
    return found

def primary_link(m, page=None, ev=None):
    """Main outbound CTA. A confirmed creator post is 'View original'. An unconfirmed direct post is
    'View credited post'. Know Your Meme and other coverage are never labeled the original."""
    if page is None:
        page = page_of(m)
    if ev is None and m.get("id"):
        ev = EVIDENCE.get(m.get("id")) or {}
    ev = ev or {}
    confirmed = None if not page else page.get("origin_confirmed")
    explicit = (page or {}).get("original_url")
    creator = explicit if is_direct_post(explicit) else None
    handle, reddit_user = credit_handles(m.get("credit"))
    if not creator and (handle or reddit_user):
        for url, blob in _creator_candidates(m, page, ev):
            if (handle and _handle_token(blob, handle)) or (reddit_user and _handle_token(blob, reddit_user)):
                creator = url
                break
    source = m.get("source_url") or ""
    if creator:
        original = confirmed is True
        return {"url": creator, "label": "View original" if original else "View credited post",
                "kind": "original" if original else "credited"}
    if is_direct_post(source):
        # Missing, null, or false origin_confirmed must not be labeled the original.
        original = confirmed is True
        return {"url": source, "label": "View original" if original else "View credited post",
                "kind": "original" if original else "credited"}
    if is_kym_url(source):
        return {"url": source, "label": "Know Your Meme explainer", "kind": "explainer"}
    if source:
        return {"url": source, "label": "View source", "kind": "source"}
    return {"url": "", "label": "View source", "kind": "source"}

def outbound(m):
    link = primary_link(m)
    return safe_url(link["url"] or m.get("source_url") or "", context="outbound")

def compact_count(n):
    n = int(n)
    if n >= 1_000_000:
        s = f"{n / 1_000_000:.1f}"
        return (s[:-2] if s.endswith(".0") else s) + "M"
    if n >= 10_000:
        s = f"{n / 1_000:.1f}"
        return (s[:-2] if s.endswith(".0") else s) + "K"
    if n >= 1_000:
        return f"{n:,}"
    return str(n)

def _observed(block):
    """The record's own checked date. Never the page build timestamp."""
    day = (block or {}).get("checked")
    return f" (observed {day})" if day else ""

def _metric_phrase(block, prefer):
    if not block:
        return None
    if prefer == "views" and block.get("views"):
        return f"{compact_count(block['views'])} views"
    if prefer == "likes" and block.get("likes"):
        return f"{compact_count(block['likes'])} likes"
    if block.get("views"):
        return f"{compact_count(block['views'])} views"
    if block.get("likes"):
        return f"{compact_count(block['likes'])} likes"
    return None

def evidence_parts(ev):
    """One phrase per platform in ev. Observation dates stay on the platform that was checked."""
    ev = ev or {}
    parts = []
    x = ev.get("x") or {}
    bits = []
    if x.get("views"):
        bits.append(f"{compact_count(x['views'])} views")
    if x.get("likes"):
        bits.append(f"{compact_count(x['likes'])} likes")
    if bits:
        who = ""
        xm = re.search(r"x\.com/([^/]+)/status/\d+", x.get("url") or "")
        if xm:
            who = f"@{xm.group(1)} "
        parts.append((x.get("url"), f"X {who}{' / '.join(bits)}{_observed(x)}"))
    t = ev.get("tiktok") or {}
    bits = []
    if t.get("views"):
        bits.append(f"{compact_count(t['views'])} views")
    if t.get("likes"):
        bits.append(f"{compact_count(t['likes'])} likes")
    if bits:
        who = (t.get("author") or "").strip()
        if who and not who.startswith("@"):
            who = "@" + who
        parts.append((t.get("url"), f"TikTok {who + ' ' if who else ''}{' / '.join(bits)}{_observed(t)}"))
    ig = ev.get("instagram") or {}
    bits = []
    if ig.get("likes"):
        bits.append(f"{compact_count(ig['likes'])} likes")
    elif ig.get("views"):
        bits.append(f"{compact_count(ig['views'])} views")
    if bits:
        who = (ig.get("author") or "").strip()
        if who and not who.startswith("@"):
            who = "@" + who
        parts.append((ig.get("url"), f"Instagram {who + ' ' if who else ''}{' / '.join(bits)}{_observed(ig)}"))
    rd = ev.get("reddit") or {}
    if rd.get("sub") and rd.get("rank"):
        parts.append((rd.get("url"), f"Reddit r/{rd['sub']} #{rd['rank']}{_observed(rd)}"))
    yt = ev.get("youtube") or {}
    if yt.get("views"):
        parts.append((yt.get("url"), f"YouTube {yt.get('channel') or 'YouTube'} {compact_count(yt['views'])} views{_observed(yt)}"))
    if ev.get("kym_views"):
        parts.append((None, f"Know Your Meme {int(ev['kym_views']):,} page views (no separate observation time on file)"))
    return parts

def evidence_sentence(ev):
    parts = evidence_parts(ev)
    return "; ".join(text for _, text in parts) + ("." if parts else "")

def why_text(m, live_evidence):
    """Live pages quote ev. Archive pages keep the snapshot's own note, including its older counts."""
    if live_evidence:
        sentence = evidence_sentence(EVIDENCE.get(m.get("id")) or {})
        if sentence:
            return sentence
    return m.get("notes") or ""

def chip_count(ev, url):
    if not ev or not url:
        return None
    for key, prefer in (("tiktok", "views"), ("x", "views"), ("youtube", "views"), ("instagram", "likes")):
        block = ev.get(key) or {}
        if block.get("url") == url:
            return _metric_phrase(block, prefer)
    return None

def synced_also_name(m, a, live_evidence):
    name = a.get("name") or ""
    if not live_evidence:
        return name
    count = chip_count(EVIDENCE.get(m.get("id")) or {}, a.get("url"))
    if not count:
        return name
    base = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    return f"{base} ({count})"

def norm_caption(s):
    s = (s or "").replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", s).strip().lower()

def strip_wrapping_quotes(s):
    s = str(s or "").strip()
    if len(s) >= 2 and s[0] in "\"'\u201c\u2018" and s[-1] in "\"'\u201d\u2019":
        return s[1:-1].strip()
    return s

def source_wordings(card_text="", source_url="", source_posts=None):
    """Complete wording from source records only. Explainer and origin prose are not accepted.
    card_text counts only together with a direct post URL. source_posts are {text, url, kind}
    and likewise need a direct post URL. A Know Your Meme URL is not provenance for a caption."""
    recs, seen = [], set()
    def add(text, url, kind):
        text = strip_wrapping_quotes(text)
        if not text or not is_direct_post(url):
            return
        key = (norm_caption(text), url)
        if key in seen:
            return
        seen.add(key)
        recs.append({"text": text, "url": url, "kind": kind})
    add(card_text, source_url, "card_text")
    for rec in source_posts or []:
        add(rec.get("text"), rec.get("url"), rec.get("kind") or "source_post")
    return recs

def match_source_wording(caption, records):
    """Exact complete match only. A fragment of a source text is not that source text."""
    if caption is None or "[" in str(caption) or "]" in str(caption):
        return None
    c = norm_caption(caption)
    if not c:
        return None
    for rec in records or []:
        if norm_caption(rec.get("text")) == c:
            return rec
    return None

def sourced_captions(captions, card_text="", source_url="", source_posts=None):
    """Keep a caption only when it equals a complete source record. Our own prose is not a source."""
    records = source_wordings(card_text, source_url, source_posts)
    kept = []
    for cap in captions or []:
        if match_source_wording(cap, records) and cap not in kept:
            kept.append(cap)
    return kept[:2]

def caption_records_for(m, info):
    """Source-post records for one meme page. Explainer and origin text are ignored.
    card_text and an attributed post-card quote count only with a direct post URL."""
    info = info or {}
    ids = list(info.get("ids") or [])
    if m.get("id") and m.get("id") not in ids:
        ids.append(m.get("id"))
    quote = (POST_CARDS.get(info.get("slug")) or {}).get("quote")
    pairs = []
    if m.get("card_text"):
        pairs.append((m.get("card_text"), m.get("source_url"), "card_text"))
    if quote:
        pairs.append((quote, m.get("source_url"), "post_card"))
    for i in ids:
        row = CANDIDATE_CARDS.get(i) or {}
        if row.get("card_text"):
            pairs.append((row["card_text"], row.get("source_url") or m.get("source_url"), "card_text"))
        if quote and row.get("source_url"):
            pairs.append((quote, row["source_url"], "post_card"))
    seen, posts = set(), []
    for text, url, kind in pairs:
        recs = source_wordings(
            card_text=text if kind == "card_text" else "",
            source_url=url if kind == "card_text" else "",
            source_posts=None if kind == "card_text" else [{"text": text, "url": url, "kind": kind}])
        for rec in recs:
            key = (norm_caption(rec["text"]), rec["url"], rec["kind"])
            if key in seen:
                continue
            seen.add(key)
            posts.append(rec)
    return posts

_COUNT_TAIL = re.compile(
    r"\s*\((?:~?\d[\d.,]*\s*[KMBkmb]?)\s+(?:views|likes|page views)\)\s*$", re.I)

def short_source_label(name):
    """Drop a trailing view/like count from a link label. Other parentheses stay."""
    name = name or ""
    short = _COUNT_TAIL.sub("", name).strip()
    return short or name

def human_list(items):
    items = [str(x) for x in items if x]
    if len(items) <= 1:
        return ", ".join(items)
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + ", and " + items[-1]

def pretty_day(value):
    try:
        return fmt_long(datetime.date.fromisoformat(str(value)[:10]))
    except Exception:
        return str(value or "")

def card_dek(m):
    """First sentence of the stored explainer. Not a new joke, and not the title repeated."""
    page = page_of(m)
    if not page or not page.get("explainer"):
        return ""
    text = page.get("blurb") or ""
    if text.startswith("Ranked by MemeStand:"):
        return ""
    return text

def source_entries(m, live_evidence):
    """Unique outbound links. The same URL is not listed twice when source and also match."""
    out, seen = [], set()
    def add(url, name):
        if not url or url in seen:
            return
        seen.add(url)
        out.append((url, name or "Source"))
    src_name = "Know Your Meme explainer" if is_kym_url(m.get("source_url")) else (m.get("source_name") or "Source")
    add(m.get("source_url"), src_name)
    for a in m.get("also") or []:
        add(a.get("url"), synced_also_name(m, a, live_evidence))
    return out

def link_row(entries, short):
    parts = []
    for url, name in entries:
        ok = safe_url(url, context="source link")
        if not ok:
            continue
        label = short_source_label(name) if short else name
        parts.append(f'<a class="src" href="{e(ok)}" target="_blank" rel="noopener">{e(label)}</a>')
    return "".join(parts)

def _url_key(url):
    return (url or "").split("?")[0].rstrip("/")

def other_source_entries(m, live_evidence):
    """Links other than the primary credit button. That button stays the visible creator source."""
    primary = _url_key(primary_link(m).get("url") or m.get("source_url"))
    return [(url, name) for url, name in source_entries(m, live_evidence) if _url_key(url) != primary]

def caption_zones(head, dek, hist, credit_html, others_html, fold_html, rank=""):
    """Description, rank note, attribution, other links, and details, each its own band.
    A rank mark hangs in the lead only; later bands stay full width under that block."""
    lead = f'{rank}<div class="lead-copy">{head}{dek}</div>' if rank else f'{head}{dek}'
    parts = [f'<div class="zone zone-lead">{lead}</div>']
    if hist and hist.strip():
        parts.append(f'<div class="zone zone-hist">{hist.strip()}</div>')
    if credit_html and credit_html.strip():
        parts.append(f'<div class="zone zone-by">{credit_html.strip()}</div>')
    if others_html:
        parts.append(f'<div class="zone zone-src"><div class="meta">{others_html}</div></div>')
    if fold_html and fold_html.strip():
        parts.append(f'<div class="zone zone-more">{fold_html.strip()}</div>')
    return "\n  ".join(parts)

def credit(m):
    c = m.get("credit") or f'via {m.get("source_name", "the source")}'
    if c[:1].islower():
        c = c[:1].upper() + c[1:]
    card = " Shown as an attributed post card of that post, not a screenshot." if uses_post_card(m) else ""
    link = primary_link(m)
    href = safe_url(link["url"] or m.get("source_url") or "", context="credit")
    go = (f'\n  <p class="go"><a href="{e(href)}" target="_blank" rel="noopener">{e(link["label"])}</a></p>'
          if href else "")
    return (f'<p class="credit"><span class="who">{e(c)}.{card}</span> '
            f'<span class="rights">&copy; its owner; shown in small form for ranking and commentary.</span></p>{go}')

def details_block(m, live_evidence):
    """Counts, observation dates, and full source labels. Closed until the reader asks."""
    entries = source_entries(m, live_evidence)
    parts = []
    bits = []
    seen = [s for s in (m.get("sources") or []) if s]
    if len(seen) > 1:
        bits.append("Seen on " + e(human_list(seen)))
    if m.get("first_seen"):
        fs = str(m["first_seen"])
        bits.append(f'First seen online <time datetime="{e(fs[:10])}">{e(pretty_day(fs))}</time>')
    if bits:
        parts.append("<p>" + ". ".join(bits) + ".</p>")
    if live_evidence:
        sentence = why_text(m, True)
        if sentence:
            parts.append(f"<p>{e(sentence)}</p>")
    full = link_row(entries, short=False)
    if full:
        parts.append(f'<p class="srcrow">{full}</p>')
    if not parts:
        return ""
    return ('<details class="fold"><summary>Sources &amp; details</summary>'
            f'<div class="foldbody">{"".join(parts)}</div></details>')

def meme_href(m, base):
    """Relative link to the meme's own page, or None (removed / unknown)."""
    sl = None if m.get("removed") else SLUG.get(m.get("id"))
    return f"{base}meme/{sl}/" if sl and sl in PAGES else None

def hl_link(m, base):
    h = meme_href(m, base)
    title = display_title(m.get("title"))
    if h: return f'<a href="{e(h)}">{e(title)}</a>'
    ok = safe_url(m.get("source_url") or "", context="headline")
    if not ok:
        return f'<a href="#">{e(title)}</a>'
    return f'<a href="{e(ok)}" target="_blank" rel="noopener">{e(title)}</a>'

def history_html(m, day, live):
    """Subtle daily-list note. Empty for weekly/monthly, removed rows, and thin history."""
    ident = meme_identity(m, SLUG)
    if not ident or not day:
        return ""
    notes = history_notes(ident, day, RANK_DAYS, live=live)
    if not notes:
        return ""
    spans = "".join(f'<span class="mv-{n["kind"]}" title="{e(n["title"])}">{e(n["text"])}</span>' for n in notes)
    return f'\n  <div class="mv">{spans}</div>'

def rank_digits(rank):
    """Visible rank is the bare number. Screen readers hear it from the heading."""
    try:
        return str(int(rank))
    except (TypeError, ValueError):
        return str(rank)

def hanging_rank(rank):
    return f'<span class="rk" aria-hidden="true">{rank_digits(rank)}</span>'

def rank_for_reader(rank):
    return f'<span class="sr-only">Rank {rank_digits(rank)}. </span>'

def item(m, base, label, notes=False, hist="", live_evidence=False):
    del notes  # checked figures live in Sources & details; this flag no longer adds a second line
    if m.get("removed"):
        return (f'<li><div class="copy"><div class="zone zone-lead">{hanging_rank(m["rank"])}'
                f'<div class="lead-copy"><h3 class="hl">{rank_for_reader(m["rank"])}{e(REMOVED)}</h3></div></div>'
                f'<div class="meta"><a class="src" href="{base}dmca.html">Takedown policy</a></div></div></li>')
    pic = thumb(m, base, label)
    heard = rank_for_reader(m["rank"])
    if pic:
        # The picture is the meme. The full headline stays in the link for search and screen readers, clamped on screen.
        head = f'<h3 class="hl clip">{heard}{hl_link(m, base)}</h3>'
    else:
        # A text post has no photo. Show its words once, not again as a second headline.
        head = f'<h3 class="hl textmeme">{heard}{text_face(m, base)}</h3>'
    dek = ""
    if live_evidence:
        text = card_dek(m)
        if text:
            dek = f'\n  <p class="dek">{e(text)}</p>'
    others = link_row(other_source_entries(m, live_evidence), short=True)
    fold = details_block(m, live_evidence)
    body = caption_zones(head, dek, hist, credit(m), others, fold, rank=hanging_rank(m["rank"]))
    return f'''<li>
  {pic}
  <div class="copy">
  {body}
  </div>
</li>'''

def column(d, p, base, link=True, notes=False, day=None, live=False, live_evidence=False):
    info = PERIODS[p]
    h = f'<a href="{base}{info["slug"]}/">{info["h2"]}</a>' if link else info["h2"]
    lis = []
    for m in d[p]:
        hist = history_html(m, day, live) if p == "daily" else ""
        lis.append(item(m, base, info["word"], notes, hist, live_evidence=live_evidence))
    return f'<section class="col" id="{p}"><h2>{h}</h2><ul>{"".join(lis)}</ul></section>'

def top_story(d, base, kicker="TODAY'S LEAD MEME", day=None, live_evidence=False):
    t = lead_of(d, day or TODAY)
    if t.get("removed"): return ""
    pic = thumb(t, base, "today", "topimg", eager=True)
    if pic:
        head = f'<h2 class="hl clip"><span class="kick">{kicker}</span>{hl_link(t, base)}</h2>'
    else:
        head = f'<h2 class="hl textmeme"><span class="kick">{kicker}</span>{text_face(m=t, base=base, cls="card topimg")}</h2>'
    dek = ""
    if live_evidence:
        text = card_dek(t)
        if text:
            dek = f'\n  <p class="dek">{e(text)}</p>'
    others = link_row(other_source_entries(t, live_evidence), short=True)
    fold = details_block(t, live_evidence)
    body = caption_zones(head, dek, "", credit(t), others, fold)
    return f'''<div class="top">
  {pic}
  <div class="copy">
  {body}
  </div>
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
             "Fields: explainer = 2-4 sentence plain-English meaning; origin = who/where/when if verified and how it spread, in our own words "
             "('\\n\\n' between paragraphs); origin_confirmed = true only if the first post/creator is documented, false if unknown (the page then "
             "says so), null = not yet researched and must not be labeled the original; how_to_use = 0-2 captions that exactly equal "
             "a source card_text or post-card quote tied to a direct post URL (explainer and origin prose are not evidence; [] if none); "
             "original_url = verified creator post when one is documented "
             "(View original uses it only when origin_confirmed is true; never drop it on a refresh); sources = [{name,url}] links that back the text (must return "
             "200); checked = ISO datetime (PT) the text was last written or reviewed (feeds dateModified + sitemap lastmod). "
             "build.py adds a stub (explainer null) for any new ranked meme; the daily routine fills it in (UPDATE.md step 5). "
             "Optional seo_title is the full public title (do not append another brand suffix). Optional meta_description replaces the generated meta description. "
             "A written explainer or origin stays on /meme/<slug>/ after the meme leaves the ranked lists. "
             "An entry with a written date stays too, so a meme that has ranked keeps its page after it drops, even before the explainer is filled in. "
             "An entry with no text and no written date does not get a page. "
             "Sitemap lastmod and dateModified use checked when it is set. "
             "Know Your Meme is an explainer, not the original post.")
SLUG, PAGES = {}, {}          # candidate id -> slug ; slug -> page info
MOMENTUM = {}                 # slug -> {series, status, delta, window} from archive scores
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

def content_stamp(checked, fallback):
    """When the explainer text was last written or reviewed.
    A newer ranking snapshot is not a content edit, so it does not move sitemap lastmod."""
    if checked:
        try:
            return datetime.datetime.fromisoformat(checked).astimezone(PT)
        except (TypeError, ValueError):
            pass
    return fallback

def written_stamp(day):
    try:
        d = datetime.date.fromisoformat(str(day)[:10])
    except Exception:
        d = NOW.date()
    return datetime.datetime(d.year, d.month, d.day, 12, 0, tzinfo=PT)

def has_written_explainer(ent):
    """Real explainer copy. A null stub is not a page we should invent."""
    return bool(str((ent or {}).get("explainer") or "").strip() or str((ent or {}).get("origin") or "").strip())

def display_row(sl, ent):
    """Enough of a ranking row to render an explainer that is no longer on a list."""
    mid = next((i for i in (ent.get("ids") or []) if i), None)
    src = CANDIDATE_DISPLAY.get(mid) or {}
    image = src.get("image") or ""
    if image and not str(image).startswith("http") and not (ROOT / image).exists():
        image = ""
    source_url = ent.get("source_url") or src.get("source_url") or ""
    source_name = src.get("source_name") or ""
    if not source_name:
        sources = ent.get("sources") or []
        if sources:
            source_name = sources[0].get("name") or ""
    return {
        "id": mid, "title": src.get("title") or ent.get("name") or sl,
        "image": image, "image_url": src.get("image_url") or "", "image_kind": src.get("image_kind") or "",
        "source_url": source_url, "source_name": source_name, "credit": src.get("credit") or "",
        "card_text": src.get("card_text") or "", "also": src.get("also") or [],
        "first_seen": src.get("first_seen") or "", "notes": src.get("notes") or "",
        "sources": src.get("sources") or [],
    }

def page_from_store(sl, ent):
    """Page record for a written explainer that is absent from every ranking snapshot."""
    m = display_row(sl, ent)
    full = ent.get("status") == "full" and bool(ent.get("explainer")) and bool(ent.get("origin"))
    published = written_stamp(ent.get("written"))
    modified = content_stamp(ent.get("checked"), published)
    return {"slug": sl, "name": ent.get("name") or sl, "explainer": ent.get("explainer"), "origin": ent.get("origin"),
            "status": "full" if full else "short", "kym_url": ent.get("kym_url"),
            "origin_confirmed": ent.get("origin_confirmed"), "how_to_use": ent.get("how_to_use") or [],
            "ids": ent.get("ids") or [], "sources": ent.get("sources", []), "related": ent.get("related", []),
            "original_url": ent.get("original_url"), "written": ent.get("written"),
            "seo_title": ent.get("seo_title") or "", "meta_description": ent.get("meta_description") or "",
            "days": [], "best": {}, "latest": m, "rows": [],
            "published": published.isoformat(timespec="seconds"),
            "modified": modified.isoformat(timespec="seconds"),
            "blurb": first_sentence(ent.get("explainer")) or f"Ranked by MemeStand: {tc(m['title'])}."}

def retain_written_pages(ents):
    """Keep a URL after a meme leaves the lists.

    A written explainer stays. So does any store entry with a `written` date, which
    build.py sets the day a meme first ranks. That is what keeps a same-day page up
    after the meme drops out of the top 10, including before anyone fills in the text.
    An entry with neither text nor a written date is not a page.
    """
    for sl, ent in ents.items():
        if sl in PAGES:
            continue
        if has_written_explainer(ent) or ent.get("written"):
            PAGES[sl] = page_from_store(sl, ent)

def public_title(info):
    custom = str(info.get("seo_title") or "").strip()
    if custom:
        return custom
    phrase = meme_phrase(info.get("name") or "")
    head = phrase.replace(" meme", " Meme") if phrase.endswith(" meme") else phrase
    return f"{head}: Meaning & Origin | MemeStand"

def public_desc(info, phrase, first_dd):
    custom = str(info.get("meta_description") or "").strip()
    if custom:
        return custom
    if info.get("explainer"):
        desc = f"{phrase} meaning: {first_sentence(info['explainer'], max(40, 146 - len(phrase)))}"
        if len(desc) < 135:
            desc += " Origin and sources."
        return desc
    if first_dd:
        return f"The {phrase} on MemeStand: first ranked {fmt_short(first_dd)}, with its source, ranking history and daily reports."
    return f"The {phrase} on MemeStand: what it means, where it came from, and the sources on file."

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
                        "origin_confirmed": None, "how_to_use": [],
                        "source_url": latest.get("source_url"), "kym_url": kym_of(latest), "sources": [], "related": [],
                        "written": seen[mid][0][0], "checked": None}
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
        modified = content_stamp(ent.get("checked"), parse_dt(snapd[days[-1]]))
        PAGES[sl] = {"slug": sl, "name": ent["name"], "explainer": ent.get("explainer"), "origin": ent.get("origin"),
                     "status": "full" if full else "short", "kym_url": ent.get("kym_url"),
                     "origin_confirmed": ent.get("origin_confirmed"), "how_to_use": ent.get("how_to_use") or [],
                     "ids": ent.get("ids") or [],
                     "sources": ent.get("sources", []), "related": ent.get("related", []),
                     "original_url": ent.get("original_url"), "written": ent.get("written"),
                     "seo_title": ent.get("seo_title") or "", "meta_description": ent.get("meta_description") or "",
                     "days": days, "best": best, "latest": latest, "rows": rows,
                     "published": parse_dt(snapd[days[0]]).isoformat(timespec="seconds"),
                     "modified": modified.isoformat(timespec="seconds"),
                     "blurb": first_sentence(ent.get("explainer")) or f"Ranked by MemeStand: {tc(latest['title'])}."}
    retain_written_pages(ents)

def sort_key(name): return re.sub(r"^[^a-z0-9]+", "", name.lower())
def az_order(): return sorted(PAGES, key=lambda sl: (sort_key(PAGES[sl]["name"]), sl))

def meme_phrase(name):
    """'X meme' unless the name already ends in meme(s)/trend."""
    return name if re.search(r"\b(memes?|trend)$", name, re.I) else f"{name} meme"

def meme_q(name):
    """FAQ / H2 questions: 'What does the X meme mean?' / 'What do the X memes mean?'."""
    phrase = meme_phrase(name)
    do = "do" if re.search(r"memes$", phrase, re.I) else "does"
    return f"What {do} the {phrase} mean?", f"Where did the {phrase} come from?"

def related_for(sl):
    """Editor-curated same-meme links only. Sharing a ranking day is not topical relatedness."""
    me = PAGES[sl]
    out = []
    for o in me.get("related") or []:
        if o in PAGES and o != sl and o not in out:
            out.append(o)
    return out[:5]

def az_meta(info):
    """A-Z line. A written page can exist before any daily report has saved it."""
    days = info.get("days") or []
    if not days:
        return "Not on a saved daily report"
    best = best_rank_text(info)
    seen = f"First seen {fmt_short(datetime.date.fromisoformat(days[0]))}"
    return f"{seen} | Best rank: {best}" if best else seen

def best_rank_text(info, link_base=None):
    parts = []
    for p in PERIODS:
        if p in info["best"]:
            r, day = info["best"][p]
            dd = fmt_short(datetime.date.fromisoformat(day))
            when = f'<a href="{link_base}archive/{day}.html">{dd}</a>' if link_base is not None else dd
            parts.append(f"#{r} {PERIODS[p]['word']} ({when})")
    return "; ".join(parts)

def live_row(mid):
    """Current memes.json row for a living page. Archive snapshots are left untouched."""
    for p in PERIODS:
        for row in data.get(p) or []:
            if row.get("id") == mid and not row.get("removed"):
                return row
    return None

def load_momentum(snaps):
    """Score trend for every meme page. Reads archive scores; does not rank or rewrite them."""
    global MOMENTUM
    days, by = [], {}
    for day, snap in snaps:
        merged = {}
        for mid, sc in momentum.score_on_day(snap).items():
            sl = SLUG.get(mid) or mid
            if sl not in merged or sc > merged[sl]:
                merged[sl] = sc
        days.append(day)
        by[day] = merged
    window = days[-momentum.WINDOW:]
    before = [d for d in days if d not in set(window)]
    out = {}
    for sl in PAGES:
        series = [by.get(d, {}).get(sl) for d in window]
        seen_before = any(by.get(d, {}).get(sl) is not None for d in before)
        out[sl] = {"series": series, "status": momentum.status_of(series, seen_before),
                   "delta": momentum.week_delta(series), "window": list(window)}
    MOMENTUM = out
    return out

def origin_block(info, m):
    """Where it started: stored origin text, plus the first source and credit already on file.

    Returns (html, plain). Both are empty when there is no origin text and no safe source URL.
    Nothing is invented to fill the gap.
    """
    prose = paras(info.get("origin"))
    role = primary_link(m, page=info)
    url = safe_url(role.get("url") or "", context="origin source")
    credit = str(m.get("credit") or "").strip().rstrip(".")
    name = str(m.get("source_name") or "").strip()
    confirmed = info.get("origin_confirmed") is True and role.get("kind") == "original" and bool(url)
    parts_html, parts_plain = [], []
    if prose:
        parts_html.append("".join(f"<p>{e(x)}</p>" for x in prose))
        parts_plain.append(" ".join(prose))
    if prose and info.get("origin_confirmed") is False:
        note = ("The original creator of this meme hasn\u2019t been confirmed. "
                "This section states only what the linked sources show.")
        parts_html.append(f'<p class="note">{e(note)}</p>')
        parts_plain.append(note)
    if url:
        lead = "First known source" if confirmed else "Earliest source on file"
        # The credit is the existing attribution. Prefer it over the ranked source name,
        # which can be a Know Your Meme page while the link is the creator's post.
        link_text = credit or role.get("label") or name or "source"
        line = f'{lead}: <a href="{e(url)}" target="_blank" rel="noopener">{e(link_text)}</a>.'
        plain = f"{lead}: {link_text} ({url})."
        if credit and link_text != credit:
            line += f" Credit: {e(credit)}."
            plain += f" Credit: {credit}."
        parts_html.append(f"<p>{line}</p>")
        parts_plain.append(plain)
    if not parts_html:
        return "", ""
    return "".join(parts_html), " ".join(parts_plain)

def trending_block(info, base):
    """Why it's trending, from this meme's archive scores and ranks. Empty when none of that is on file."""
    mom = MOMENTUM.get(info.get("slug")) or {}
    series = mom.get("series") or []
    status = mom.get("status")
    days = info.get("days") or []
    html_parts, plain_parts = [], []
    if days:
        first = datetime.date.fromisoformat(days[0])
        html_parts.append(
            f'<p>First seen on MemeStand <a href="{base}archive/{e(days[0])}.html">{fmt_long(first)}</a>.</p>')
        plain_parts.append(f"First seen on MemeStand {fmt_long(first)}.")
        peak_html = best_rank_text(info, base)
        peak_plain = best_rank_text(info, None)
        if peak_html:
            html_parts.append(f"<p>Peak rank: {peak_html}.</p>")
            plain_parts.append(f"Peak rank: {peak_plain}.")
        items, names = [], []
        for d in reversed(days):
            dd = datetime.date.fromisoformat(d)
            items.append(f'<li><a href="{base}archive/{e(d)}.html">Daily Meme Report, {fmt_long(dd)}</a></li>')
            names.append(fmt_long(dd))
        html_parts.append("<h3>Daily meme reports featuring it</h3><ul>" + "".join(items) + "</ul>")
        plain_parts.append("Daily meme reports: " + "; ".join(names) + ".")
    fs = (info.get("latest") or {}).get("first_seen")
    if fs:
        shown = pretty_day(fs)
        if shown:
            html_parts.append(f"<p>Ranked post or trend first seen online: {e(shown)}.</p>")
            plain_parts.append(f"Ranked post or trend first seen online: {shown}.")
    if status:
        html_parts.append(f'<p>Current status: <a href="{base}meme-index/#method">{e(status)}</a>.</p>')
        plain_parts.append(f"Current status: {status}.")
    scored = [s for s in series if s is not None]
    if scored:
        text = momentum.fmt_score(scored[-1])
        html_parts.append(f"<p>Latest momentum score on file: {e(text)}.</p>")
        plain_parts.append(f"Latest momentum score on file: {text}.")
    if not html_parts:
        return "", ""
    return "".join(html_parts), " ".join(plain_parts)

def build_meme_page(sl):
    info, base = PAGES[sl], "../../"
    url, name, m = f"{SITE}/meme/{sl}/", info["name"], info["latest"]
    live = live_row(m.get("id"))
    if live and live.get("title"):
        m = dict(m)
        m["title"] = live["title"]
    phrase = meme_phrase(name)
    h1 = f"{phrase}: meaning and origin"
    title = public_title(info)
    days = info["days"]
    first_dd = datetime.date.fromisoformat(days[0]) if days else None
    desc = public_desc(info, phrase, first_dd)
    sections = []
    if str(info.get("explainer") or "").strip():
        sections.append(("What it means", "".join(f"<p>{e(x)}</p>" for x in paras(info["explainer"])),
                         " ".join(paras(info["explainer"]))))
    origin_html, origin_plain = origin_block(info, m)
    if origin_html:
        sections.append(("Where it started", origin_html, origin_plain))
    records = caption_records_for(m, info)
    uses = sourced_captions(info.get("how_to_use") or [], source_posts=records)
    if uses:
        sections.append(("Source caption",
                         "<ul>" + "".join(f"<li>&ldquo;{e(x)}&rdquo;</li>" for x in uses) + "</ul>",
                         "Quoted from the source: " + " / ".join("\u201c" + x + "\u201d" for x in uses)))
    trend_html, trend_plain = trending_block(info, base)
    if trend_html:
        sections.append(("Why it's trending", trend_html, trend_plain))
    rel = related_for(sl)
    if rel:
        sections.append(("Related memes",
                         "<ul>" + "".join(
                             f'<li><a href="{base}meme/{o}/">{e(meme_phrase(PAGES[o]["name"]))}</a>: {e(PAGES[o]["blurb"])}</li>'
                             for o in rel) + "</ul>",
                         " ".join(f"{meme_phrase(PAGES[o]['name'])}: {PAGES[o]['blurb']}" for o in rel)))
    unconf = bool(info.get("origin")) and info.get("origin_confirmed") is False
    short = ('<p class="note">This page is deliberately short: little verified information about this meme is available, '
             'so we only state what the source shows.</p>') if info.get("status") != "full" and not unconf else ""
    evidence = why_text(m, True)
    stat_bits = [f"Latest evidence on file: {e(evidence)}"] if evidence else []
    srcs, seen_u = [], set()
    def add_src(nm, u):
        ok = safe_url(u, context="meme source") if u else ""
        if ok and ok not in seen_u:
            seen_u.add(ok)
            srcs.append((nm, ok))
    role = primary_link(m, page=info)
    if role["kind"] == "original":
        add_src("Original post", role["url"])
    elif role["kind"] == "credited":
        add_src("Credited post (original creator not confirmed)", role["url"])
    if is_kym_url(m.get("source_url")):
        add_src("Know Your Meme explainer", m.get("source_url"))
    elif m.get("source_url"):
        add_src(m.get("source_name") or "Source", m.get("source_url"))
    for s_ in info.get("sources") or []:
        add_src(s_.get("name"), s_.get("url"))
    for a in m.get("also") or []:
        add_src(synced_also_name(m, a, True), a.get("url"))
    if info.get("kym_url"):
        add_src("Know Your Meme explainer", info["kym_url"])
    src_html = "".join(f'<li><a href="{e(u)}" target="_blank" rel="noopener">{e(nm)}</a></li>' for nm, u in srcs)
    primary_url = _url_key(role.get("url"))
    short_links = "".join(
        f'<a class="src" href="{e(u)}" target="_blank" rel="noopener">{e(short_source_label(nm))}</a>'
        for nm, u in srcs if _url_key(u) != primary_url)
    src_zone = f'<div class="zone zone-src"><div class="meta">{short_links}</div></div>' if short_links else ""
    stat_html = "".join(f"<p>{bit}</p>" for bit in stat_bits)
    detail_fold = ""
    if stat_html or src_html:
        detail_fold = ('<details class="fold"><summary>Sources &amp; details</summary>'
                       f'<div class="foldbody">{stat_html}<ul>{src_html}</ul></div></details>')
    section_html = "".join(f"<h2>{e(h)}</h2>{inner}" for h, inner, _plain in sections)
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
    faq = [(h, plain) for h, _inner, plain in sections if plain]
    if faq:
        nodes.append({"@type": "FAQPage", "@id": f"{url}#faq", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]})
    og = abs_img(m) if (OG_USE_MEME_THUMB and m.get("image")) else None
    written_on = info.get("written") or (days[0] if days else "")
    reviewed = ""
    if info.get("explainer") and info.get("modified") and info["modified"][:10] != written_on:
        reviewed = "; last reviewed " + e(info["modified"][:10])
    body = f"""
{mast(base, "MEME EXPLAINED -- MEANING AND ORIGIN", h1=False)}
<nav class="crumbs" aria-label="Breadcrumb"><a href="{home_href(base)}">MemeStand</a> &rsaquo; <a href="{base}memes/">Memes A&ndash;Z</a> &rsaquo; <span aria-current="page">{e(name)}</span></nav>
<main class="prose explainer">
<article>
<h1>{e(h1)}</h1>
{thumb(m, base, "")}
<div class="copy">
<div class="zone zone-by">
{credit(m)}
</div>
{src_zone}
</div>
{section_html}
{short}
<div class="zone zone-more">
{detail_fold}
</div>
<p class="note">Written {e(written_on)}{reviewed} from the sources above. Explanations describe memes and online reactions; they are not
MemeStand's statements of fact about the people in them. Corrections or removals: {contact_html()}. Rights holders: see <a href="{base}dmca.html">DMCA / Takedowns</a>.</p>
</article>
</main>
<p class="pager"><a href="{base}memes/">All memes A&ndash;Z</a> | <a href="{base}meme-index/">Meme Index</a> | <a href="{home_href(base)}">Today's top memes</a> | <a href="{base}archive/">Daily Meme Report Archive</a></p>
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
                      f'<div class="meta">{e(az_meta(PAGES[sl]))}</div></li>'
                      for sl in sls)
        secs.append(f'<h2 id="{aid(k)}">{k}</h2><ul>{lis}</ul>')
    il = {"@type": "ItemList", "@id": f"{url}#memes", "name": "MemeStand meme explainers A\u2013Z", "numberOfItems": len(order),
          "itemListOrder": "https://schema.org/ItemListOrderAscending",
          "itemListElement": [{"@type": "ListItem", "position": i, "url": f"{SITE}/meme/{sl}/", "name": meme_phrase(PAGES[sl]["name"])}
                              for i, sl in enumerate(order, 1)]}
    wp = webpage(url, title, desc, ISO, crumbs=[("MemeStand", f"{SITE}/"), ("Memes A\u2013Z", url)], about_lists=[il["@id"]])
    body = f"""
{mast(base, "ALL MEMES A&ndash;Z -- WHAT THEY MEAN AND WHERE THEY CAME FROM")}
<nav class="crumbs" aria-label="Breadcrumb"><a href="{home_href("../")}">MemeStand</a> &rsaquo; <span aria-current="page">Memes A&ndash;Z</span></nav>
<p class="intro">{e(desc)} Every page cites its sources and links the original post.</p>
<p class="az">{jump}</p>
<main class="one">{"".join(secs)}</main>
<p class="pager"><a href="../meme-index/">Meme Index</a> | <a href="{home_href("../")}">Today's top memes</a> | <a href="../archive/">Daily Meme Report Archive</a></p>
"""
    write("memes/index.html", head(title=title, desc=desc, path="memes/", base=base, ld=[graph(ORG, WEBSITE, wp, il)]) + body + footer(base))

METHOD = ("Status is the shape of each meme's momentum score over the last 7 saved daily snapshots "
          "(fewer if the archive is shorter). One score per Pacific day: the daily list's score when the meme is on it, "
          "otherwise the highest score on the other lists that day. A day with no row is a gap, not a zero. "
          "New means the only score in that window is on the latest day and the meme has no earlier snapshot. "
          "Rising means the latest score is up from the previous score in the window and is the high of the window. "
          "Peaking means the latest score is that high and did not rise from the previous score. "
          "Fading means the latest score is below the window high, or the meme is absent from the latest day after appearing earlier. "
          "Week change compares the first day of the window with the latest day. Missing at the start means the meme entered. "
          "Missing at the end means it left. This page does not change how the top 10 is ranked.")

def _status_class(status):
    return {"Rising": "st-rising", "New": "st-new", "Peaking": "st-peaking", "Fading": "st-fading"}.get(status or "", "")

def _life_meta(sl, base):
    info = PAGES[sl]
    mom = MOMENTUM.get(sl) or {}
    bits = []
    peak = best_rank_text(info, base)
    if peak:
        bits.append("Peak " + peak)
    scored = [s for s in (mom.get("series") or []) if s is not None]
    if scored:
        bits.append("Score " + momentum.fmt_score(scored[-1]))
    return " &middot; ".join(bits)

def _life_item(sl, base, show_delta=False):
    info = PAGES[sl]
    mom = MOMENTUM.get(sl) or {}
    status = mom.get("status")
    spark = momentum.sparkline(mom.get("series") or [])
    if show_delta:
        delta = mom.get("delta")
        way = "up" if (delta or 0) > 0 else "down"
        left = f'<div class="delta {way}">{e(momentum.fmt_delta(delta))}</div>'
    else:
        left = f'<div class="{_status_class(status)}">{spark}</div>' if spark else "<div></div>"
    st = f'<div class="st {_status_class(status)}">{e(status)}</div>' if status else ""
    meta = _life_meta(sl, base)
    spark_row = f'<div class="sub">{spark}</div>' if show_delta and spark else ""
    sub = f'<div class="sub">{meta}</div>' if meta else ""
    return (f'<li>{left}<div>{st}<div class="who"><a href="{base}meme/{e(sl)}/">{e(info["name"])}</a></div>'
            f"{spark_row}{sub}</div></li>")

def build_meme_index():
    base, url = "../", f"{SITE}/meme-index/"
    title = "Meme Index: Which Memes Are Rising, Peaking, and Fading | MemeStand"
    window = next((v["window"] for v in MOMENTUM.values() if v.get("window")), [])
    if len(window) >= 2:
        span = f"{fmt_long(datetime.date.fromisoformat(window[0]))} to {fmt_long(datetime.date.fromisoformat(window[-1]))}"
    elif window:
        span = fmt_long(datetime.date.fromisoformat(window[0]))
    else:
        span = "the saved daily snapshots"
    counts = {}
    for v in MOMENTUM.values():
        if v.get("status"):
            counts[v["status"]] = counts.get(v["status"], 0) + 1
    desc = (f"MemeStand's meme index: {len(PAGES)} tracked memes, updated {fmt_short(NOW)}. "
            f"Rising, peaking, and fading from momentum scores across {span}.")
    rows = [{"slug": sl, "name": PAGES[sl]["name"], "delta": (MOMENTUM.get(sl) or {}).get("delta")} for sl in PAGES]
    up, down = momentum.movers(rows, 5)
    order = {"Rising": 0, "New": 1, "Peaking": 2, "Fading": 3}
    all_sl = sorted(PAGES, key=lambda sl: (order.get((MOMENTUM.get(sl) or {}).get("status"), 4),
                                           sort_key(PAGES[sl]["name"]), sl))
    def block(group, empty):
        if not group:
            return f'<p class="note">{e(empty)}</p>'
        return '<ul class="life">' + "".join(_life_item(r["slug"], base, show_delta=True) for r in group) + "</ul>"
    tally = ", ".join(f"{counts.get(k, 0)} {k.lower()}" for k in ("Rising", "New", "Peaking", "Fading"))
    il = {"@type": "ItemList", "@id": f"{url}#tracked", "name": "MemeStand meme index",
          "numberOfItems": len(all_sl), "itemListOrder": "https://schema.org/ItemListUnordered",
          "itemListElement": [{"@type": "ListItem", "position": i, "url": f"{SITE}/meme/{sl}/",
                               "name": meme_phrase(PAGES[sl]["name"])} for i, sl in enumerate(all_sl, 1)]}
    wp = webpage(url, title, desc, ISO, crumbs=[("MemeStand", f"{SITE}/"), ("Meme Index", url)], about_lists=[il["@id"]])
    body = f"""
{mast(base, "THE MEME INDEX", h1=False)}
<nav class="crumbs" aria-label="Breadcrumb"><a href="{home_href(base)}">MemeStand</a> &rsaquo; <span aria-current="page">Meme Index</span></nav>
<main class="prose">
<h1>Which memes are rising, peaking, and fading</h1>
<p class="intro">{e(desc)} {e(tally)}.</p>
{upd_html()}
<p class="method" id="method">{e(METHOD)} Window: {e(span)}.</p>
<h2 id="risers">Biggest risers this week</h2>
{block(up, "No tracked meme's score rose across this window.")}
<h2 id="fallers">Biggest fallers this week</h2>
{block(down, "No tracked meme's score fell across this window.")}
<h2 id="tracked">Every tracked meme</h2>
<ul class="life">{"".join(_life_item(sl, base) for sl in all_sl)}</ul>
</main>
<p class="pager"><a href="{home_href(base)}">Today's top memes</a> | <a href="{base}memes/">Memes A&ndash;Z</a> | <a href="{base}archive/">Daily Meme Report Archive</a></p>
"""
    write("meme-index/index.html", head(title=title, desc=desc, path="meme-index/", base=base,
                                        ld=[graph(ORG, WEBSITE, wp, il)]) + body + footer(base))

EMBED_SNIPPET = (
    '<iframe src="https://memestand.com/embed/top5.html" title="Top memes today from MemeStand" '
    'width="320" height="520" style="border:1px solid #bbb;max-width:100%" loading="lazy" '
    'referrerpolicy="strict-origin-when-cross-origin"></iframe>'
)

def embed_items():
    """First five daily rows that still have a meme page, in rank order."""
    out = []
    for m in data.get("daily") or []:
        if m.get("removed") or not m.get("id"):
            continue
        sl = SLUG.get(m["id"])
        if not sl or sl not in PAGES:
            continue
        href = safe_url(f"{SITE}/meme/{sl}/", context="embed")
        if not href:
            continue
        out.append((m, sl, href))
        if len(out) == 5:
            break
    return out

def build_embed():
    items = embed_items()
    lis = []
    for m, sl, href in items:
        label = PAGES[sl].get("name") or display_title(m.get("title"))
        rank = m.get("rank") if m.get("rank") is not None else ""
        lis.append(
            f'<li><span class="rk" aria-hidden="true">{e(rank)}</span>'
            f'<a class="name" href="{e(href)}" target="_blank" rel="noopener">'
            f'<span class="sr-only">Rank {e(rank)}. </span>{e(label)}</a></li>')
    home = safe_url(SITE + "/", context="embed home")
    today = safe_url(f"{SITE}/top-memes-today/", context="embed today")
    logo = safe_url(f"{SITE}/favicon.svg", context="embed logo")
    absolute = NOW.strftime("%a %b %-d, %Y %-I:%M %p PT").upper()
    widget = f'''
<div id="content" class="embed-wrap">
<p class="embed-brand"><a href="{e(home)}" target="_blank" rel="noopener"><img src="{e(logo)}" alt="" width="64" height="64"><span class="word">MEMESTAND</span></a></p>
<h1>Top memes today</h1>
<ol class="embed-list">{"".join(lis)}</ol>
<p class="embed-foot">Updated <time datetime="{ISO}">{e(absolute)}</time></p>
<p class="embed-foot"><a href="{e(today)}" target="_blank" rel="noopener">Full top 10 on MemeStand</a></p>
</div>
'''
    wtitle = "Top memes today | MemeStand"
    wdesc = f"The top memes today on MemeStand, {fmt_short(NOW)}. Each name links to that meme's page on memestand.com."
    write("embed/top5.html", head(title=wtitle, desc=wdesc, path="embed/top5.html", base="../") + widget
          + CF_ANALYTICS + "\n</body></html>\n")
    ititle = "Embed the Top Memes Today | MemeStand"
    idesc = "Add MemeStand's top memes today to your site. Copy one iframe. Each meme links back to its page on memestand.com."
    ibase, iurl = "../", f"{SITE}/embed/"
    ibody = f"""
{mast(ibase, "EMBED THE TOP MEMES TODAY")}
<nav class="crumbs" aria-label="Breadcrumb"><a href="{home_href(ibase)}">MemeStand</a> &rsaquo; <span aria-current="page">Embed</span></nav>
<main class="prose">
<p>Paste this into a page. It loads a small static frame of the first five memes on <a href="{ibase}top-memes-today/">today's list</a> that have a MemeStand page, in rank order. Each name opens that meme's page on memestand.com. The frame is rebuilt with the rest of the site, so an hourly refresh updates it. It sets no cookies. It uses the same cookieless analytics beacon as the rest of MemeStand.</p>
<h2>Copy this</h2>
<pre class="snippet">{e(EMBED_SNIPPET)}</pre>
<h2>Preview</h2>
<iframe src="top5.html" title="Top memes today from MemeStand" width="320" height="520" style="border:1px solid #bbb;max-width:100%" loading="lazy"></iframe>
<p class="note">The frame is <a href="top5.html">/embed/top5.html</a>. Link the names; don't copy the memes themselves.</p>
</main>
<p class="pager"><a href="{home_href(ibase)}">Today's top memes</a> | <a href="{ibase}meme-index/">Meme Index</a></p>
"""
    wp = webpage(iurl, ititle, idesc, ISO, crumbs=[("MemeStand", f"{SITE}/"), ("Embed", iurl)])
    write("embed/index.html", head(title=ititle, desc=idesc, path="embed/", base=ibase, ld=[graph(ORG, WEBSITE, wp)])
          + ibody + footer(ibase))

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

def period_switch(current, base):
    """Links between the daily, weekly, and monthly lists."""
    keys = [k for k in PERIODS if k != current]
    return " | ".join(f'<a href="{base}{PERIODS[k]["slug"]}/">{PERIODS[k]["h2"].title()}</a>' for k in keys)

def build_home():
    d, url = data, f"{SITE}/"
    t1 = tc(d["daily"][0]["title"])
    title = "MemeStand — Daily Meme Report: Today's Top Memes, Ranked by Virality"
    desc = (f"MemeStand's daily meme report: today's top memes and the best of the month, "
            f"ranked by virality. Today's #1 ({fmt_short(NOW)}): \"{t1}\".")
    og, og_alt = og_for(d)
    lists = [itemlist(d, p, url, fmt_short(NOW)) for p in MAIN_PERIODS]
    ld = graph(ORG, WEBSITE, webpage(url, title, desc, ISO, about_lists=[x["@id"] for x in lists]), *lists)
    page = head(title=title, desc=desc, path="", base="", og_img=og, og_alt=og_alt or "MemeStand: top 10 memes today and this month", ld=[ld]) + f'''
{mast("", "THE TOP MEMES TODAY &amp; THIS MONTH -- RANKED BY VIRALITY")}
<p class="intro">{e(INTRO)} See the full <a href="top-memes-today/">top 10 memes today</a>, <a href="trending-memes-this-week/">trending memes this week</a>, and <a href="best-memes-this-month/">best memes of the month</a>.</p>
{upd_html()}
{top_story(d, "", live_evidence=True)}
<main class="grid two">
  {column(d, "daily", "", day=TODAY, live=True, live_evidence=True)}
  {column(d, "monthly", "", live_evidence=True)}
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
        desc = f"Today's top memes, {fmt_long(NOW)}: #1 is \"{t}\". The 10 most viral memes of the last 24-36 hours, ranked with the evidence from X, TikTok, Instagram, Reddit, YouTube and Know Your Meme."
    elif p == "weekly":
        start = NOW.date() - datetime.timedelta(days=6)
        title = f"Trending Memes This Week — Top 10 ({start.strftime('%b %-d')}–{fmt_short(NOW)}) | MemeStand"
        h1 = f"TRENDING MEMES THIS WEEK -- TOP 10 ({start.strftime('%b %-d').upper()} - {fmt_short(NOW).upper()})"
        desc = f"The top 10 trending memes this week ({start.strftime('%b %-d')}–{fmt_short(NOW)}): #1 is \"{t}\". Ranked by cross-platform virality, updated through the day."
    else:
        title = f"Best Memes of {NOW.strftime('%B %Y')} — Top 10 Memes This Month | MemeStand"
        h1 = f"BEST MEMES OF THE MONTH -- TOP 10, LAST 30 DAYS"
        desc = f"The best memes of the month (last 30 days, updated {fmt_short(NOW)}): #1 is \"{t}\". The 10 biggest memes ranked by reach and cross-platform spread."
    lst = itemlist(d, p, url, fmt_short(NOW))
    crumbs = [("MemeStand", f"{SITE}/"), (info["h2"].title(), url)]
    m1 = d[p][0]
    og = abs_img(m1) if (OG_USE_MEME_THUMB and m1.get("image") and not m1.get("removed")) else None
    ld = graph(ORG, WEBSITE, webpage(url, title, desc, ISO, crumbs=crumbs, about_lists=[lst["@id"]]), lst)
    others = period_switch(p, "../")
    page = head(title=title, desc=desc, path=f"{info['slug']}/", base=base, og_img=og, og_alt=alt(m1, info["word"]) if og else None, ld=[ld]) + f'''
{mast(base, h1)}
<p class="intro">{INTRO}</p>
{upd_html()}
<main class="one">{column(d, p, base, link=False, notes=True, day=TODAY if p == "daily" else None, live=True, live_evidence=True)}</main>
<p class="pager">{others} | <a href="../archive/">Daily Meme Report Archive</a></p>
''' + footer(base)
    write(f"{info['slug']}/index.html", page)

def snapshot_replaces(existing, incoming):
    """True only when incoming memes.json is a newer evidence refresh.
    An equal or older updated stamp must not replace frozen ranks, notes, or counts.
    Takedown scrub does not use this decision: it edits matching rows in place."""
    try:
        return parse_dt(incoming) > parse_dt(existing)
    except Exception:
        return True

def snapshots():
    ARCH_DATA.mkdir(parents=True, exist_ok=True)
    snap = ARCH_DATA / f"{TODAY}.json"
    txt = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    write_today = not snap.exists()
    if snap.exists():
        try:
            write_today = snapshot_replaces(json.loads(snap.read_text()), data)
        except Exception:
            write_today = True
    if write_today and (not snap.exists() or snap.read_text() != txt):
        snap.write_text(txt)
    out = []
    for f in sorted(ARCH_DATA.glob("????-??-??.json")):
        try:
            # Blocklist removals still apply when updated was not bumped. scrub replaces only the
            # matching row and keeps its rank; other rows' notes, scores, and order stay.
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
    else: pager.append(f'<a href="{home_href(base)}">Live rankings &rarr;</a>')
    page = head(title=title, desc=desc, path=f"archive/{day}.html", base=base, og_img=og, og_alt=og_alt,
                og_type="article", ld=[graph(ORG, WEBSITE, wp, *lists)], modified=iso) + f'''
{mast(base, f"DAILY MEME REPORT -- {fmt_long(dd).upper()}")}
<p class="intro">The internet's top memes as ranked by MemeStand on {fmt_long(dd)}. Rankings below are frozen as of <time datetime="{iso}">{dt.strftime("%-I:%M %p PT")}</time> that day; see the homepage for live rankings.</p>
<p class="pager">{" ".join(pager)}</p>
{top_story(d, base, kicker=f"LEAD MEME OF {fmt_short(dd).upper()}", day=day)}
<main class="grid">
  {column(d, "daily", base, link=False, day=day, live=False)}
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
                   f'<div class="meta">#1: {e(display_title(d["daily"][0]["title"]))}</div></li>' for day, d in reversed(snaps))
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
    desc = "MemeStand ranks the top 10 memes today, this week and this month using a virality evidence score built from X, TikTok, Instagram, Reddit, YouTube and Know Your Meme data."
    body = f"""<h2>What is MemeStand?</h2>
<p>MemeStand (memestand.com) is an independent, headline-style daily meme report. The lists, updated hourly from 6 AM to 9 PM Pacific, are
the <a href="top-memes-today/">top 10 memes today</a>, <a href="trending-memes-this-week/">trending memes this week</a>, and the <a href="best-memes-this-month/">best memes of the month</a> (last 30 days).
Each day's rankings are saved in the
<a href="archive/">daily meme report archive</a> and published in an <a href="feed.xml">Atom feed</a>.
The <a href="meme-index/">meme index</a> shows which tracked memes are rising, peaking, or fading. Other sites can embed the
<a href="embed/">top memes today</a>.</p>
<h2>How are memes ranked?</h2>
<p>Each candidate meme gets a <b>virality evidence score</b>. Every meme listed links to a real, checked source post or entry.</p>
<table><tr><th>Signal</th><th>Points</th></tr>
<tr><td>X: views of the best post (or 10 &times; likes when only likes are known)</td><td>10 &times; log10(views); 1M = 60, 10M = 70</td></tr>
<tr><td>TikTok: views of the best public post we could read (or a count cited by Know Your Meme)</td><td>10 &times; log10(views) &minus; 5; 10M = 65, 30M = 70</td></tr>
<tr><td>Instagram: likes on the best public post (logged-out pages show likes, not plays)</td><td>10 &times; log10(likes &times; 10) &minus; 5; 1M likes = 65</td></tr>
<tr><td>YouTube: views of the best video about the meme (10,000+ views)</td><td>10 &times; log10(views) + 5; 100K = 55, 1M = 65</td></tr>
<tr><td>Reddit top-feed position (r/memes, r/dankmemes)</td><td>#1 = 60-62, &minus;2 per rank</td></tr>
<tr><td>Combined reach: the best platform score, plus a share of the next two</td><td>best + 10% of 2nd + 5% of 3rd (each platform capped at 75)</td></tr>
<tr><td>Each additional source with confirmed evidence (of X, TikTok, Instagram, Reddit, YouTube, Know Your Meme)</td><td>+3 (max +12)</td></tr>
<tr><td>Picked in a Know Your Meme editorial, Weekly Roundup or Meme of the Month poll</td><td>+3</td></tr>
<tr><td>X trending news story about it</td><td>+5</td></tr>
<tr><td>Know Your Meme page views &ge; 50,000</td><td>+5</td></tr></table>
<p>Each platform is scored on its own scale, so a platform where views come cheaply (TikTok) can't drown out the others, and a meme
that shows up on several platforms beats one that is big in a single place. TikTok and Instagram have no open trending lists, so
their numbers come from public post pages we open (usually posts that Know Your Meme cites for the meme) or from counts Know Your
Meme reports; we don't see the whole platform, so their coverage is partial.</p>
<p>Windows: <b>today</b> = took off in the last ~36 hours; <b>this week</b> = active in the last 7 days; <b>this month</b> = active in the last 30 days.
Engagement numbers come from the platforms' public pages and APIs and from Know Your Meme as they stood when we checked them; they can change or be wrong.
On a live list, Sources &amp; details repeats those checked figures and the date of each check. That date is not the page's Updated time.</p>
<p>On the daily top 10, a short note under the headline is computed from earlier daily archive files and the meme's stable page: <b>New today</b> means it is on today's list and was not on yesterday's; <b>First time</b> is added only when no earlier daily archive contains it and the archive has no missing day; <b>Up</b>, <b>Down</b>, or <b>Unchanged since yesterday</b> is the rank change; <b>N days at #1</b> counts a consecutive run of at least two Pacific days. An hourly refresh does not add a day. If a day's archive is missing, that note is left off. The weekly and monthly lists do not show these notes.</p>

<h2 id="policy">Content and editorial policy</h2>
<ul>
<li><b>What we pick:</b> memes with public, checkable evidence of spread. We never invent memes, numbers, links, or punchlines. A caption on an explainer is a quotation from the source, or it is left off.</li>
<li><b>Credit:</b> every item names who posted it when that is known. &ldquo;View original&rdquo; is used only when the meme page's origin is explicitly confirmed. Otherwise a direct post is &ldquo;View credited post&rdquo;. An unresearched page is not labeled the original. Know Your Meme is an explainer, not the original. Thumbnails are small (400&nbsp;px max, metadata stripped) and link to that same post.</li>
<li><b>Counts and dates:</b> on the live lists, each platform's views or likes are the figure stored for that check, with that check's date, under Sources &amp; details. The &ldquo;Updated&rdquo; line is only when the page was built. A dated archive page keeps the counts recorded that day. We do not write a new observation time just to look current.</li>
<li><b>Headlines:</b> headlines describe the meme and how people are reacting to it. They are not MemeStand's statements of fact about anyone. When a meme is about an allegation or controversy involving a real person, the headline says so and names the source (for example, &ldquo;per KYM&rdquo;); we don't repeat unverified claims as fact. Jokes and parody are labeled as jokes.</li>
<li><b>What we leave out:</b> sexually explicit or nude content; hate speech and memes that demean people for race, ethnicity, national origin, religion, sex, sexual orientation, gender identity or disability; content that sexualizes, targets or identifies minors; graphic violence or gore; self-harm; harassment or doxxing of private individuals; and anything a rights holder asks us to remove. When in doubt, we leave it out.</li>
<li><b>Corrections and removals:</b> if a headline is wrong or unfair, or you want your content removed, {contact_html()}. Copyright notices follow our <a href="dmca.html">DMCA policy</a>.</li>
<li><b>Independence:</b> MemeStand is not affiliated with, endorsed by or sponsored by X, TikTok, Instagram, Reddit, YouTube, Know Your Meme or anyone featured. Names of platforms and people are used only to identify sources and subjects. Nobody pays to be ranked.</li>
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
<li><b>Trademarks.</b> X, TikTok, Instagram, Reddit, YouTube, Know Your Meme and other names belong to their owners and are used only to identify sources. MemeStand is not
affiliated with, endorsed by or sponsored by any of them or by anyone featured on the site, and a meme's appearance here is not an
endorsement by us or by them.</li>
</ul>

<h2>3. Takedowns</h2>
<p>If you own something on MemeStand and want it removed, see our <a href="dmca.html">DMCA and takedown policy</a>.</p>

<h2>4. Third-party sites and content</h2>
<p>MemeStand links to, and may display images from, sites we don't control, such as X, TikTok, Instagram, Reddit, YouTube and Know Your Meme. Their content, terms and
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
<p>We don't set cookies or use advertising or social-media tracking. The JavaScript on our pages is: (1) the Cloudflare Web Analytics
beacon described above, and (2) a tiny first-party inline script on ranking pages that rewrites the "Updated" stamp into a relative
"X min/hours ago" label in your browser from the build timestamp already in the page (no cookies, no network calls, no fingerprinting),
and (3) a tiny first-party inline script for the light/dark theme button, which saves your choice (just "light" or "dark") in your
browser's localStorage; it is never sent to us.
The other script tags are structured data (JSON-LD) that search engines read and browsers don't execute.</p>

<h2>Third-party content and links</h2>
<p>Thumbnails are served from memestand.com. If an item shows an image directly from its source platform (for example X, Reddit,
Know Your Meme, TikTok, Instagram or YouTube), your browser fetches it from that platform, which may then see your IP address and browser details; we tell browsers
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
        def feed_li(m):
            if m.get("removed"):
                return f"<li>{e(m['title'])}</li>"
            ok = safe_url(m.get("source_url") or "", context="feed")
            credit = e(m.get("credit") or m["source_name"])
            if not ok:
                return f"<li>{e(m['title'])} ({e(m['source_name'])}; credit: {credit})</li>"
            return f"<li>{e(m['title'])} (<a href=\"{e(ok)}\">{e(m['source_name'])}</a>; credit: {credit})</li>"
        lis = "".join(feed_li(m) for m in d["daily"])
        img = None if t.get("removed") else abs_img(t)
        if img and safe_url(img, context="feed image") != img:
            img = None
        imgh = f'<p><img src="{e(img)}" alt="{e(alt(t, "today"))}"{wh_attrs(img_src(t)) if img_dims(img_src(t)) else ""}></p>' if img else ""
        if t.get("removed"):
            first = e(t["title"])
        else:
            ok = safe_url(t.get("source_url") or "", context="feed lead")
            first = f"<a href=\"{e(ok)}\">{e(t['title'])}</a>" if ok else e(t["title"])
        content = (f"{imgh}<p>#1 meme of {fmt_long(dd)}: {first}</p><p>Top 10 memes today:</p><ol>{lis}</ol>"
                   f"<p>Memes &copy; their respective owners; MemeStand is not affiliated with X, TikTok, Instagram, Reddit, YouTube or Know Your Meme.</p>")
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
    urls += [("memes/", ISO, "daily", "0.7"), ("meme-index/", ISO, "daily", "0.8"),
             ("embed/", ISO, "monthly", "0.4"), ("embed/top5.html", ISO, "daily", "0.3")]
    urls += [(f"meme/{sl}/", PAGES[sl]["modified"], "weekly", "0.6") for sl in az_order()]
    body = "".join(f"<url><loc>{SITE}/{u}</loc>{f'<lastmod>{lm}</lastmod>' if lm else ''}<changefreq>{cf}</changefreq><priority>{pr}</priority></url>\n"
                   for u, lm, cf, pr in urls)
    write("sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}</urlset>\n')

BOTS = ["Googlebot", "Google-Extended", "Bingbot", "GPTBot", "OAI-SearchBot", "ChatGPT-User", "PerplexityBot", "Perplexity-User",
        "ClaudeBot", "Claude-SearchBot", "Claude-User", "anthropic-ai", "Applebot", "Applebot-Extended", "DuckDuckBot",
        "CCBot", "Meta-ExternalAgent", "Amazonbot", "cohere-ai", "MistralAI-User", "YouBot", "xAI-Bot", "GrokBot"]
# Google Search Console URL-prefix verification for https://memestand.com/
# (memestandhq@gmail.com). Google re-fetches this URL, so do not remove it after
# verification. The body is the downloaded token: one line, no trailing newline, no HTML.
# prune_meme_pages() only deletes stale meme/<slug>/ directories, so a committed root
# file would already survive a build. Rewriting the bytes here also restores the file
# if a refresh deletes it or wraps it in a page template. Not a page: no analytics beacon.
GSC_FILE = "google327e53c932d0bf40.html"
GSC_BODY = b"google-site-verification: google327e53c932d0bf40.html"

def build_search_console():
    p = ROOT / GSC_FILE
    if not p.exists() or p.read_bytes() != GSC_BODY:
        p.write_bytes(GSC_BODY)
    written.append(GSC_FILE)

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
    def hist(m):
        ident = meme_identity(m, SLUG)
        notes = history_notes(ident, TODAY, RANK_DAYS, live=True) if ident else []
        return (" — " + "; ".join(n["text"] for n in notes)) if notes else ""
    def lst(p):
        return "\n".join(f"{m['rank']}. {REMOVED}" if m.get("removed") else
                         f"{m['rank']}. {tc(m['title'])} — source: {m['source_url']} — credit: {m.get('credit') or m['source_name']}"
                         + (hist(m) if p == "daily" else "")
                         + (f" — evidence: {m['notes']}" if m.get("notes") else "")
                         + (f" — explainer: {SITE}/{meme_href(m, '')}" if meme_href(m, "") else "")
                         for m in data[p])
    write("llms.txt", f"""# MemeStand

> MemeStand (https://memestand.com) is an independent, headline-style daily meme report. The lists are the top 10 memes today, trending memes this week, and the best memes of the month (last 30 days). Ranked by a cross-platform virality score built from X (Twitter) engagement and trending stories, TikTok post views, Instagram post likes, Reddit top feeds (r/memes, r/dankmemes), YouTube video views and Know Your Meme. Updated hourly, 6 AM to 9 PM Pacific Time. Every listed meme links to its original source.

Last updated: {NOW.strftime("%Y-%m-%d %H:%M")} PT ({ISO})

## Key pages

- [Homepage — top 10 memes today and this month]({SITE}/): the live report
- [Top 10 memes today]({SITE}/top-memes-today/): the most viral memes of the last 24-36 hours, with evidence
- [Best memes of the month]({SITE}/best-memes-this-month/): top 10 memes of the last 30 days
- [Trending memes this week]({SITE}/trending-memes-this-week/): the top 10 memes of the last 7 days
- [Daily meme report archive]({SITE}/archive/): one dated page per day, e.g. {SITE}/archive/{TODAY}.html
- [All memes A–Z]({SITE}/memes/): index of MemeStand's per-meme explainer pages
- [Meme Index]({SITE}/meme-index/): which tracked memes are rising, peaking, or fading, from archived momentum scores. It does not change the top 10.
- [Embed the top memes today]({SITE}/embed/): iframe snippet for the top 5. The frame itself is {SITE}/embed/top5.html
- Meme explainer pages ({SITE}/meme/<slug>/): what each meme means, where it started (only when a source is on file), why it is trending on MemeStand, and related memes. A page stays up after the meme leaves the top 10.
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

- On the daily top 10, New today, First time, Up/Down/Unchanged since yesterday, and "N days at #1" come only from archived daily rankings and the meme's stable page identity. A missing archive day leaves the note off. Hourly refreshes do not add a day. Weekly and monthly lists do not carry these notes.
- Cite MemeStand as "MemeStand (memestand.com) daily meme report" and link the dated archive page for a specific day.
- Rankings change daily; the archive pages are permanent snapshots (items removed after a takedown request are marked as removed).
- Headlines describe memes and online reactions; they are not MemeStand's statements of fact about the people involved. Where a headline mentions a claim about a person, it is attributed to its source.
- Meme explainer pages state only what the ranked source post, the linked creator posts, or Know Your Meme document. Know Your Meme is an explainer. "View original" is used only when origin_confirmed is true. Captions must match a stored post text (card_text or post-card quote) tied to a direct post URL. Wording in the explainer is not a source. A "short" page means little verified information exists, not that anything was guessed.
- Live "Sources & details" counts come from each platform's checked evidence and carry that observation date. The Updated stamp is the page build time. Archive pages keep the counts stored for that day.
- The memes themselves belong to their creators and owners. MemeStand is independent and not affiliated with, endorsed by or sponsored by X, TikTok, Instagram, Reddit, YouTube, Know Your Meme or any person or brand mentioned.
""")

def main():
    global RANK_DAYS
    snaps = snapshots()
    meme_registry(snaps)
    load_momentum(snaps)
    # One rank map per Pacific archive day, after slugs exist. Today's file is the latest hourly list.
    RANK_DAYS = {day: daily_ranks(d.get("daily") or [], SLUG) for day, d in snaps}
    lead_why = choose_leads(snaps)
    build_home()
    for p in PERIODS: build_period(p)
    for i, (day, d) in enumerate(snaps):
        build_archive_day(day, d, snaps[i - 1][0] if i else None, snaps[i + 1][0] if i + 1 < len(snaps) else None)
    build_archive_index(snaps)
    for sl in sorted(PAGES): build_meme_page(sl)
    build_memes_index()
    build_meme_index()
    build_embed()
    prune_meme_pages()
    build_about()
    build_dmca()
    build_terms()
    build_privacy()
    build_feed(snaps)
    build_sitemap(snaps)
    build_robots()
    build_search_console()
    build_llms()
    full = sum(1 for v in PAGES.values() if v["status"] == "full")
    print(f"built {len(written)} files ({len(snaps)} archive day(s), {len(PAGES)} meme pages: {full} full, {len(PAGES) - full} short); latest report {TODAY}")
    stubs = sorted(sl for sl, v in PAGES.items() if not v["explainer"])
    _st = json.loads(STORE.read_text())["memes"]
    gaps = {sl: [k for k, bad in (("explainer", not v["explainer"]), ("origin", not v["origin"]),
                                  ("origin_confirmed", _st.get(sl, {}).get("origin_confirmed") is None),
                                  ("sources", not (v["sources"] or v["kym_url"])), ("checked", not _st.get(sl, {}).get("checked"))) if bad]
            for sl, v in PAGES.items()}
    gaps = {sl: g for sl, g in sorted(gaps.items()) if g}
    print(f"  lead {TODAY}: {LEADS.get(TODAY)} ({lead_why})")
    if stubs: print("  ! WARNING: meme pages still need explainer/origin text in data/meme_pages.json:", ", ".join(stubs))
    for sl, g in gaps.items():
        if sl not in stubs: print(f"  ! WARNING: meme page {sl} is missing {', '.join(g)} in data/meme_pages.json")

if __name__ == "__main__":
    main()
