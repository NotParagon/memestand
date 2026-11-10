#!/usr/bin/env python3
"""URL allowlist and CSP hash checks. Run: python3 tools/test_safe_url.py

The built-page check reads the HTML already on disk, so run python3 build.py first.
"""
import contextlib
import io
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import build
import rank
import safe_url as su

ROOT = pathlib.Path(__file__).resolve().parent.parent

GOOD = [
    "https://example.com/a",
    "https://example.com/a?b=1&c=2",
    "https://example.com/a#frag",
    "HTTPS://Example.com/A",
    "https://user:pass@example.com/a",
    "/images/a.jpg",
    "/",
    "images/a.jpg",
    "../meme/x/",
    "./",
    "#content",
    "?q=1",
    "top-memes-today/",
]

BAD = [
    "javascript:alert(1)",
    "JAVASCRIPT:alert(1)",
    "JaVaScRiPt:alert(1)",
    "java\tscript:alert(1)",
    "java\nscript:alert(1)",
    "java\rscript:alert(1)",
    "java\x0bscript:alert(1)",
    "\njavascript:alert(1)",
    "\tjavascript:alert(1)",
    " javascript:alert(1)",
    "https://example.com/\n",
    " https://example.com/a",
    "https://example.com/a ",
    "data:text/html,<script>alert(1)</script>",
    "data:image/png;base64,aaaa",
    "vbscript:msgbox(1)",
    "VBSCRIPT:msgbox(1)",
    "http://example.com/a",
    "HTTP://example.com/a",
    "https:example.com/a",
    "https://",
    "https:///",
    "//evil.example/a.js",
    "///evil.example/a",
    "/\\evil.example/a",
    "\\evil.example/a",
    "javascript:alert(1)\\",
    "mailto:hello@memestand.com",
    "file:///etc/passwd",
    "java\u200bscript:alert(1)",
    "java\u0000script:alert(1)",
    "https://example.com\\@evil.example/",
]


def test_allowlist_and_warnings():
    for raw in GOOD:
        su.reset_warnings()
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            got = su.safe_url(raw)
        assert got == raw, (raw, got)
        assert buf.getvalue() == "", (raw, buf.getvalue())
        assert su.safe_url(got) == got
    for raw in BAD:
        su.reset_warnings()
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            got = su.safe_url(raw, context="test")
        assert got == "", (raw, got)
        log = buf.getvalue()
        assert "WARNING" in log and "dropped unsafe URL" in log, (raw, log)
    su.reset_warnings()
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        assert su.safe_url("") == ""
        assert su.safe_url(None) == ""
        assert su.safe_url("javascript:alert(1)") == ""
        assert su.safe_url("javascript:alert(1)") == ""  # same value warns once
    assert buf.getvalue().count("WARNING") == 1


def test_rank_rejects_bad_urls_before_write():
    su.reset_warnings()
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        assert rank.accepted_url("https://x.com/a/status/1", "source_url", "ok") == "https://x.com/a/status/1"
        assert rank.accepted_url("javascript:alert(1)", "source_url", "bad") == ""
        assert rank.accepted_url("http://example.com/a", "image_url", "bad") == ""
        assert rank.accepted_url("java\tscript:alert(1)", "image_url", "tab") == ""
        assert rank.accepted_url("//cdn.example/a.jpg", "image_url", "proto") == ""
        assert rank.accepted_url("", "source_url", "empty") == ""
        assert rank.accepted_url(None, "source_url", "none") == ""
        also = rank.accepted_also([
            {"name": "Bad", "url": "data:text/html,hi"},
            {"name": "Http", "url": "http://insecure.example/a"},
            {"name": "Ok", "url": "https://example.com/ok"},
            {"name": "No url"},
        ], "meme")
        assert rank.fetch_image({"id": "nope"}, "javascript:alert(1)") is None
        assert rank.fetch_image({"id": "nope"}, "") is None
    assert also == [{"name": "Ok", "url": "https://example.com/ok"}, {"name": "No url"}]
    log = buf.getvalue()
    assert "source_url for bad" in log
    assert "image_url for bad" in log
    assert "also.url for meme" in log


def test_rendered_href_and_src_drop_bad_urls():
    su.reset_warnings()
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        html = build.item({
            "rank": 4,
            "id": "not-a-real-meme-safe-url",
            "title": "Hello",
            "source_url": "javascript:alert(1)",
            "source_name": "Evil",
            "credit": "via Evil",
            "also": [
                {"name": "Data", "url": "data:text/html,hi"},
                {"name": "Http", "url": "http://insecure.example/a"},
                {"name": "Proto", "url": "//evil.example/a"},
                {"name": "Tab", "url": "java\tscript:alert(1)"},
                {"name": "Ok", "url": "https://example.com/ok"},
            ],
        }, "", "today")
        words = build.text_face({
            "rank": 1, "id": "not-a-real-meme-safe-url", "title": "Hi",
            "source_url": "vbscript:msgbox(1)", "source_name": "V",
        }, "")
        blank = build.thumb({
            "rank": 1, "id": "not-a-real-meme-safe-url", "title": "Hi",
            "image": "data:text/html,hi", "source_url": "https://example.com/a", "source_name": "S",
        }, "", "today")
        http_img = build.thumb({
            "rank": 1, "id": "not-a-real-meme-safe-url", "title": "Hi",
            "image_url": "http://cdn.example/a.jpg", "source_url": "https://example.com/a", "source_name": "S",
        }, "", "today")
        tab_img = build.thumb({
            "rank": 1, "id": "not-a-real-meme-safe-url", "title": "Hi",
            "image": "java\tscript:alert(1)", "source_url": "https://example.com/a", "source_name": "S",
        }, "", "today")
        hot = build.thumb({
            "rank": 1, "id": "not-a-real-meme-safe-url", "title": "Hi",
            "image_url": "https://cdn.example/a.jpg", "source_url": "https://example.com/post", "source_name": "S",
        }, "", "today")
        local = build.thumb({
            "rank": 1, "id": "seatbelt-dog", "title": "Seatbelt Dog",
            "image": "images/seatbelt-dog.jpg", "source_url": "https://x.com/acervodoguinhos/status/1",
            "source_name": "X",
        }, "../", "today")
    low = html.lower()
    assert "javascript:" not in low
    assert "data:text" not in low
    assert "http://insecure" not in low
    assert "//evil.example" not in low
    assert "java" not in low or "https://example.com/ok" in html
    assert "javascript" not in low
    assert "https://example.com/ok" in html
    assert 'href="#"' in html
    assert "vbscript:" not in words.lower()
    assert 'href="#"' in words
    assert blank == "" and http_img == "" and tab_img == ""
    assert 'src="https://cdn.example/a.jpg"' in hot
    assert 'href="https://example.com/post"' in hot
    assert 'src="../images/seatbelt-dog.jpg"' in local
    assert 'href="https://x.com/acervodoguinhos/status/1"' in local
    assert "WARNING" in buf.getvalue()


def test_csp_hashes_match_emitted_scripts_and_skip_jsonld():
    page = build.head(title="T", desc="D", path="", base="",
                      ld=[{"@context": "https://schema.org", "@type": "WebSite", "name": "MemeStand"}])
    assert '<meta name="referrer" content="strict-origin-when-cross-origin">' in page
    meta = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)">', page)
    assert meta, page[:500]
    policy = meta.group(1)
    assert policy == (
        "default-src 'self'; "
        "script-src 'self' https://static.cloudflareinsights.com "
        + " ".join(f"'{build.script_hash(body)}'" for body in _inline_bodies())
        + "; connect-src 'self' https://cloudflareinsights.com; "
        "img-src 'self' https: data:; "
        "media-src 'self' https:; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self' https: data:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    assert "frame-ancestors" not in policy
    script_src = policy.split("script-src ", 1)[1].split(";", 1)[0]
    assert "'unsafe-inline'" not in script_src
    assert "https://static.cloudflareinsights.com" in script_src
    assert "https://static.cloudflareinsights.com/beacon.min.js" in build.CF_ANALYTICS
    # The meta is before the theme script, so the policy applies to it.
    assert page.index("Content-Security-Policy") < page.index(build.THEME_HEAD)
    ld_bodies = re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
    assert ld_bodies
    for body in ld_bodies:
        assert build.script_hash(body) not in policy
    _assert_page_scripts(page + build.THEME_TOGGLE + build.UPD_SCRIPT + build.CF_ANALYTICS)


def _inline_bodies():
    bodies = []
    for chunk in (build.THEME_HEAD, build.THEME_TOGGLE, build.UPD_SCRIPT):
        bodies.extend(build.executable_inline_bodies(chunk))
    assert len(bodies) == 3
    return bodies


def _assert_page_scripts(text, path=""):
    meta = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)">', text)
    assert meta, path
    policy = meta.group(1)
    assert 'name="referrer" content="strict-origin-when-cross-origin"' in text
    assert "https://static.cloudflareinsights.com/beacon.min.js" in text
    assert "https://static.cloudflareinsights.com" in policy.split(";", 1)[1]
    for attrs, body in re.findall(r"<script\b([^>]*)>(.*?)</script>", text, re.I | re.S):
        if re.search(r"\bsrc\s*=", attrs, re.I):
            src = re.search(r"""\bsrc\s*=\s*['"]([^'"]+)""", attrs, re.I)
            assert src, path
            assert src.group(1).startswith("https://static.cloudflareinsights.com/"), (path, src.group(1))
            continue
        kind = re.search(r"""\btype\s*=\s*['"]?([^'"\s>]+)""", attrs, re.I)
        if kind and "ld+json" in kind.group(1).lower():
            assert build.script_hash(body) not in policy
            continue
        assert f"'{build.script_hash(body)}'" in policy, (path, body[:60])


def test_built_pages_csp_covers_every_inline_script():
    pages = [p for p in ROOT.rglob("*.html") if p.name != "google327e53c932d0bf40.html"]
    assert len(pages) > 10
    checked = 0
    for path in pages:
        text = path.read_text()
        if "<html" not in text[:400]:
            continue
        checked += 1
        _assert_page_scripts(text, path)
        assert "javascript:" not in text.lower(), path
        assert "vbscript:" not in text.lower(), path
        assert 'href="http://' not in text and "href='http://" not in text, path
        assert 'src="http://' not in text and "src='http://" not in text, path
    assert checked > 10


def main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"{len(fns)} tests passed")


if __name__ == "__main__":
    main()
