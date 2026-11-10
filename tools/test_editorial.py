#!/usr/bin/env python3
"""Provenance, sourced captions, and evidence-timestamp checks. Run: python3 tools/test_editorial.py"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import build

ROOT = pathlib.Path(__file__).resolve().parent.parent
TIKTOK = "https://www.tiktok.com/@leehoustonx/video/7703227788160961806"
KYM = "https://knowyourmeme.com/memes/your-first-time-in-a-fancy-cafe"
XPOST = "https://x.com/vibeistani/status/2116644824703279122"


def test_fancy_cafe_original_is_the_creator_post_not_kym():
    page = {"origin_confirmed": True, "original_url": TIKTOK, "sources": []}
    meme = {"id": "fancy-cafe", "source_url": KYM, "source_name": "Know Your Meme",
            "credit": "posted by @leehoustonx on TikTok", "also": []}
    link = build.primary_link(meme, page=page, ev={})
    assert link["url"] == TIKTOK
    assert link["label"] == "View original"
    assert link["kind"] == "original"
    kym_only = build.primary_link(
        {"id": "x", "source_url": KYM, "credit": "image via Know Your Meme"},
        page={"origin_confirmed": False, "sources": []}, ev={})
    assert kym_only["label"] == "Know Your Meme explainer"
    assert "knowyourmeme.com" in kym_only["url"]


def test_unconfirmed_direct_post_is_not_called_the_original():
    meme = {"id": "pakistani-citizenship", "source_url": XPOST, "source_name": "X / @vibeistani",
            "credit": "posted by @vibeistani on X"}
    for page in (None, {}, {"origin_confirmed": None}, {"origin_confirmed": False}):
        link = build.primary_link(meme, page=page, ev={})
        assert link["url"] == XPOST, page
        assert link["label"] == "View credited post", page
        assert link["kind"] == "credited"
    confirmed = build.primary_link(meme, page={"origin_confirmed": True, "sources": []}, ev={})
    assert confirmed["label"] == "View original"
    assert confirmed["url"] == XPOST
    # A confirmed flag cannot turn a Know Your Meme page into the original.
    kym = build.primary_link(
        {"id": "only-kym", "source_url": KYM, "credit": "image via Know Your Meme"},
        page={"origin_confirmed": True, "sources": []}, ev={})
    assert kym["label"] == "Know Your Meme explainer"
    assert kym["kind"] == "explainer"


def test_secondary_coverage_is_not_the_original_when_the_creator_post_is_known():
    meme = {"id": "fancy-cafe", "source_url": KYM, "credit": "posted by @leehoustonx on TikTok",
            "also": [{"name": "X News (cafe mix-up)", "url": "https://x.com/i/trending/2117626647205875908"},
                     {"name": "TikTok / @leehoustonx (11.6M views)", "url": TIKTOK}]}
    link = build.primary_link(meme, page={"origin_confirmed": True, "sources": []}, ev={})
    assert link["url"] == TIKTOK
    assert "trending" not in link["url"]
    assert "knowyourmeme" not in link["url"]


NEWTON = "If Newton saw the way I be moving these days he'd add a fourth law of motion"
NEWTON_URL = "https://x.com/sbxloch/status/2118821023151706276"


def test_sourced_captions_drop_invented_variants_and_keep_real_quotes():
    dropped = build.sourced_captions(
        ["Me confidently sitting down somewhere I've never been",
         "She only wants me for my [your country] passport."],
        card_text="she only wants me for my pakistani citizenship",
        source_url=XPOST)
    assert dropped == []
    kept = build.sourced_captions(
        [NEWTON, "If Newton saw the way [player] is moving these days, he'd add a fourth law of motion"],
        card_text=NEWTON, source_url=NEWTON_URL)
    assert kept == [NEWTON]


def test_explainer_quotes_do_not_make_a_caption_sourced():
    invented = "Me confidently sitting down somewhere I've never been"
    # The old check treated this sentence, once pasted into the explainer, as evidence.
    assert build.sourced_captions([invented], card_text="", source_url=TIKTOK) == []
    assert build.sourced_captions(
        [invented],
        source_posts=[{"text": invented, "url": KYM, "kind": "explainer"}]) == []
    assert build.match_source_wording(invented, build.source_wordings(
        card_text=f'People say "{invented}" about the clip.', source_url=TIKTOK)) is None


def test_partial_source_text_is_not_a_caption():
    assert build.sourced_captions(
        ["If Newton saw the way I be moving"],
        card_text=NEWTON, source_url=NEWTON_URL) == []
    longer = NEWTON + " And then he danced."
    assert build.sourced_captions([longer], card_text=NEWTON, source_url=NEWTON_URL) == []
    assert build.sourced_captions([NEWTON], card_text=NEWTON, source_url=KYM) == []


def test_unsupported_caption_is_removed():
    assert build.sourced_captions(
        ["Gotta be one of my favorite genders"],
        card_text="she only wants me for my pakistani citizenship",
        source_url=XPOST) == []
    assert build.sourced_captions(["Woke 3 starts tonight"]) == []


def test_store_captions_match_a_direct_post_record():
    import json
    pages = json.loads((ROOT / "data" / "meme_pages.json").read_text())["memes"]
    cands = {c["id"]: c for c in json.loads((ROOT / "data" / "candidates.json").read_text())["candidates"]}
    kept = []
    banned = [
        "Me confidently sitting down somewhere I've never been",
        "She only wants me for my [your country] passport",
        "Frutiger Aero yams to your right",
        "Woke 3 starts tonight",
        NEWTON,
        "let the man rest",
    ]
    for sl, ent in pages.items():
        blob = " ".join(ent.get("how_to_use") or [])
        for bad in banned:
            assert bad not in blob, sl
        for cap in ent.get("how_to_use") or []:
            mid = ent["ids"][0]
            row = cands[mid]
            meme = {"id": mid, "source_url": row.get("source_url"), "card_text": row.get("card_text")}
            recs = build.caption_records_for(meme, {"slug": sl, "ids": ent["ids"]})
            hit = build.match_source_wording(cap, recs)
            assert hit, (sl, cap)
            assert hit["kind"] in ("card_text", "post_card")
            assert build.is_direct_post(hit["url"])
            assert build.sourced_captions([cap]) == []
            kept.append((sl, cap, hit["kind"], hit["url"]))
    assert kept == [(
        "bounce-baby-boy",
        "Boys go always bounce back na why dem dey call us bouncing baby boy",
        "post_card",
        "https://x.com/2THUQQ/status/2118617523708965188",
    )]


def test_evidence_line_uses_the_checked_observation_not_the_page_build():
    ev = build.EVIDENCE["fancy-cafe"]
    sentence = build.evidence_sentence(ev)
    count = build.chip_count(ev, TIKTOK)
    assert count and count in sentence
    assert f"observed {ev['tiktok']['checked']}" in sentence
    assert "11.1M" not in sentence
    assert "21:09" not in sentence
    assert "6AM" not in sentence
    # The same TikTok URL contributes the same count to the chip and the sentence.
    assert count in sentence
    # Know Your Meme's page-view field has no checked clock, so it must not borrow the page build time.
    assert "no separate observation time on file" in sentence
    stale = {"id": "fancy-cafe", "notes": "TikTok @leehoustonx 11.1M views (Nov 6 6AM PT)."}
    assert count.split()[0] in build.why_text(stale, True)
    assert "11.1M" not in build.why_text(stale, True)
    assert build.why_text(stale, False).startswith("TikTok @leehoustonx 11.1M")


def test_archive_labels_are_not_rewritten_from_later_evidence():
    meme = {"id": "fancy-cafe", "also": [{"name": "TikTok / @leehoustonx (10.9M views)", "url": TIKTOK}]}
    assert build.synced_also_name(meme, meme["also"][0], False) == "TikTok / @leehoustonx (10.9M views)"
    live = build.chip_count(build.EVIDENCE["fancy-cafe"], TIKTOK)
    assert build.synced_also_name(meme, meme["also"][0], True) == f"TikTok / @leehoustonx ({live})"


def test_related_links_are_only_the_curated_list():
    saved = dict(build.PAGES)
    build.PAGES.clear()
    build.PAGES.update({
        "she-only-wants-me-for-my-pakistani-citizenship": {
            "related": [], "rows": [("2026-11-01", "daily", {"rank": 4})], "best": {"daily": (4, "2026-11-01")}},
        "snow-leopard-paws-at-you": {
            "related": [], "rows": [("2026-11-01", "daily", {"rank": 2})], "best": {"daily": (2, "2026-11-01")}},
        "heidi-32gb-ram": {
            "related": ["sam-altman-ram"], "rows": [], "best": {"daily": (3, "2026-11-01")}},
        "sam-altman-ram": {
            "related": ["heidi-32gb-ram"], "rows": [], "best": {"daily": (1, "2026-11-01")}},
    })
    try:
        assert build.related_for("she-only-wants-me-for-my-pakistani-citizenship") == []
        assert "snow-leopard-paws-at-you" not in build.related_for("she-only-wants-me-for-my-pakistani-citizenship")
        assert build.related_for("heidi-32gb-ram") == ["sam-altman-ram"]
    finally:
        build.PAGES.clear()
        build.PAGES.update(saved)


def test_equal_timestamp_does_not_replace_a_frozen_archive():
    old = {"updated": "2026-11-07T21:09:00-08:00", "daily": [{"id": "a", "notes": "11.1M"}]}
    same = {"updated": "2026-11-07T21:09:00-08:00", "daily": [{"id": "a", "notes": "11.6M"}]}
    newer = {"updated": "2026-11-07T22:00:00-08:00", "daily": same["daily"]}
    assert build.snapshot_replaces(old, same) is False
    assert build.snapshot_replaces(old, newer) is True


def test_blocklist_scrub_keeps_neighbor_evidence_without_a_new_stamp():
    rows = [
        {"rank": 1, "id": "keep", "notes": "11.1M views (Nov 6 6AM PT).", "title": "KEEP", "score": 70.0},
        {"rank": 2, "id": "drop", "title": "DROP ME", "source_url": XPOST, "notes": "gone", "score": 10},
    ]
    blocked = build.blocked_by(rows[1], [{"id": "drop", "reason": "takedown"}])
    assert blocked
    out = []
    for m in rows:
        if not m.get("removed") and build.blocked_by(m, [{"id": "drop"}]):
            out.append({"rank": m["rank"], "removed": True, "title": build.REMOVED})
        else:
            out.append(m)
    assert out[0]["notes"] == rows[0]["notes"] and out[0]["score"] == 70.0
    assert out[1] == {"rank": 2, "removed": True, "title": build.REMOVED}
    # The stamp is not consulted. A frozen updated time does not block this row edit.
    assert build.snapshot_replaces(
        {"updated": "2026-11-07T21:09:00-08:00"},
        {"updated": "2026-11-07T21:09:00-08:00"}) is False


def test_list_h1_is_the_headline_and_weekly_is_in_the_nav():
    head = build.mast("", "THE TOP MEMES TODAY")
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", head).group(1)
    assert h1 == "THE TOP MEMES TODAY"
    assert "MEMESTAND" not in h1
    assert head.index('<span class="logo">') < head.index("<h1")
    assert 'href="trending-memes-this-week/"' in head
    assert 'href="top-memes-today/"' in head
    assert 'href="best-memes-this-month/"' in head
    plain = build.mast("../../", "MEME EXPLAINED", h1=False)
    assert "<h1" not in plain
    assert "MEMESTAND" in plain
    foot = build.footer("")
    assert 'href="trending-memes-this-week/">Trending This Week</a>' in foot
    switch = build.period_switch("daily", "../")
    assert "trending-memes-this-week/" in switch
    assert "best-memes-this-month/" in switch


def test_custom_public_title_is_not_suffixed_again():
    custom = "Crack a Monster Meme ('It's Not That Deep'): Meaning & Origin | MemeStand"
    info = {"name": "It's Not That Deep. Crack a Monster.", "seo_title": custom, "explainer": "A cope line."}
    assert build.public_title(info) == custom
    assert info["seo_title"].count("MemeStand") == 1
    plain = {"name": "Seatbelt Dog", "explainer": "A dog."}
    assert build.public_title(plain) == "Seatbelt Dog Meme: Meaning & Origin | MemeStand"
    cousins = "What My Little Cousins Do When They See Me Meme (Hippo & Alligator) | MemeStand"
    assert build.public_title({"name": "Little Cousins (Hippo and Alligator)", "seo_title": cousins}) == cousins


def test_content_stamp_prefers_the_review_time():
    import datetime
    fallback = datetime.datetime.fromisoformat("2026-11-09T14:04:00-08:00")
    got = build.content_stamp("2026-11-07T23:13:29-08:00", fallback)
    assert got.isoformat(timespec="seconds") == "2026-11-07T23:13:29-08:00"
    assert build.content_stamp(None, fallback) == fallback
    assert build.content_stamp("not-a-date", fallback) == fallback


def test_written_explainer_stays_when_it_is_off_the_lists():
    saved = dict(build.PAGES)
    blobs = {}
    real_write = build.write
    build.PAGES.clear()

    def capture(rel, text):
        blobs[rel] = text

    build.write = capture
    try:
        build.retain_written_pages({
            "kept-off-list": {
                "name": "Kept Off List",
                "ids": ["kept-off-list"],
                "explainer": "A real explanation of the joke.",
                "origin": "The first post has not been confirmed.",
                "origin_confirmed": False,
                "status": "short",
                "sources": [{"name": "Example", "url": "https://example.com/post"}],
                "written": "2026-11-04",
                "checked": "2026-11-04T12:00:00-08:00",
                "source_url": "https://x.com/someone/status/1",
            },
            "empty-stub": {"name": "Empty Stub", "ids": ["empty-stub"], "explainer": None, "origin": None},
        })
        assert "kept-off-list" in build.PAGES
        assert "empty-stub" not in build.PAGES
        assert build.PAGES["kept-off-list"]["days"] == []
        assert build.PAGES["kept-off-list"]["modified"].startswith("2026-11-04T12:00:00")
        build.build_meme_page("kept-off-list")
    finally:
        build.write = real_write
        build.PAGES.clear()
        build.PAGES.update(saved)
    html = blobs["meme/kept-off-list/index.html"]
    assert "A real explanation of the joke." in html
    assert "archive/" not in html.split("<h1", 1)[-1].split("Daily meme reports", 1)[0] or "No saved daily report" in html
    assert "No saved daily report includes this meme right now." in html
    assert "archive/2026-11-04.html" not in html


def test_home_links_do_not_use_index_html():
    assert build.home_href("") == "./"
    assert build.home_href("../../") == "../../"
    assert "index.html" not in build.mast("../../", "TAG", h1=False)
    assert "index.html" not in build.footer("../../")
    assert 'href="./"' in build.footer("")


def _hrefs(html, label):
    return re.findall(rf'<a href="([^"]+)"[^>]*>{label}</a>', html)


def test_display_title_and_source_labels():
    shout = "'POV: YOUR FIRST TIME IN A FANCY CAFE': AI-GENERATED CAFE SEATING MIX-UP"
    assert build.display_title(shout) == "'POV: Your First Time in a Fancy Cafe': AI-Generated Cafe Seating Mix-up"
    yams = "'FRUTIGER AERO YAMS': BRAINROT CATCHPHRASE TEASING FANS OF THE GLOSSY 2000s AESTHETIC GETS A KYM ENTRY"
    cased = build.display_title(yams)
    assert cased.startswith("'Frutiger Aero Yams':")
    assert "2000s" in cased
    assert "AESTHETIC" not in cased
    quoted = "X users joke that Ken Paxton 'eats salsa made in New York City'"
    assert build.display_title(quoted) == quoted
    assert build.display_title(build.REMOVED) == build.REMOVED
    assert build.short_source_label("TikTok / @leehoustonx (11.7M views)") == "TikTok / @leehoustonx"
    assert build.short_source_label("Instagram / @kevinwinnik (11M likes)") == "Instagram / @kevinwinnik"
    assert build.short_source_label("X News (cafe mix-up)") == "X News (cafe mix-up)"
    assert build.short_source_label("Credited post (original creator not confirmed)") == \
        "Credited post (original creator not confirmed)"


def test_details_keep_snapshot_counts_and_live_observation_dates():
    live = {
        "id": "fancy-cafe",
        "source_url": KYM,
        "source_name": "Know Your Meme",
        "credit": "posted by @leehoustonx on TikTok",
        "first_seen": "2026-11-01",
        "sources": ["X", "TikTok", "Instagram", "Know Your Meme"],
        "also": [{"name": "TikTok / @leehoustonx (10.9M views)", "url": TIKTOK}],
        "notes": "TikTok @leehoustonx 11.1M views",
    }
    opened = build.details_block(live, True)
    sentence = build.evidence_sentence(build.EVIDENCE["fancy-cafe"])
    assert opened.startswith("<details")
    assert "Sources &amp; details" in opened
    assert sentence in opened
    assert "11.1M" not in opened
    assert "November 1, 2026" in opened
    assert "Know Your Meme explainer" in opened
    frozen = build.details_block(live, False)
    assert "10.9M views" in frozen
    assert "11.1M" not in frozen
    assert sentence not in frozen
    build.SLUG["fancy-cafe"] = "fancy-cafe"
    build.PAGES["fancy-cafe"] = {"origin_confirmed": True, "original_url": TIKTOK, "sources": []}
    try:
        credit = build.credit(live)
    finally:
        build.SLUG.pop("fancy-cafe", None)
        build.PAGES.pop("fancy-cafe", None)
    assert "Posted by @leehoustonx on TikTok." in credit
    assert "View original" in credit
    assert TIKTOK in credit
    assert "knowyourmeme.com" not in credit
    others = build.other_source_entries(live, True)
    assert all(build._url_key(url) != TIKTOK.rstrip("/") for url, _name in others)
    assert any("knowyourmeme.com" in url for url, _name in others)
    zones = build.caption_zones("<h3>Title</h3>", "<p class=\"dek\">AI-generated video.</p>",
                                "<div class=\"mv\">note</div>", credit, "links", "<details>x</details>")
    assert zones.index("zone-lead") < zones.index("zone-hist") < zones.index("zone-by")
    assert zones.index("zone-by") < zones.index("zone-src") < zones.index("zone-more")


def test_reading_css_wraps_and_keeps_a_keyboard_focus_ring():
    css = build.CSS
    assert "overflow-wrap:anywhere" in css
    assert ".fold summary:focus-visible" in css
    assert "text-transform:none" in css or ".hl{" in css
    for rule in re.findall(r"\.hl\{[^}]+\}", css):
        assert "uppercase" not in rule, rule
    for rule in re.findall(r"\.top \.hl a\{[^}]+\}", css):
        assert "uppercase" not in rule, rule
    assert "text-transform:uppercase" in css  # section bars keep the masthead voice
    assert "--hair:" in css
    assert ".copy .zone+.zone" in css
    assert "border-top:1px solid var(--hair)" in css


def test_built_pages_match_the_rules():
    today = (ROOT / "top-memes-today" / "index.html").read_text()
    home = (ROOT / "index.html").read_text()
    fancy = (ROOT / "meme" / "fancy-cafe" / "index.html").read_text()
    cite = (ROOT / "meme" / "she-only-wants-me-for-my-pakistani-citizenship" / "index.html").read_text()
    nov5 = (ROOT / "archive" / "2026-11-05.html").read_text()
    nov6 = (ROOT / "archive" / "2026-11-06.html").read_text()
    nov7 = (ROOT / "archive" / "2026-11-07.html").read_text()
    snap = (ROOT / "data" / "archive" / "2026-11-07.json").read_text()

    originals = _hrefs(today, "View original")
    assert originals, "expected at least one View original link"
    assert all("knowyourmeme.com" not in u for u in originals)
    # Fancy Cafe left the daily list and stays on the weekly list. Do not put it back on daily.
    week = (ROOT / "trending-memes-this-week" / "index.html").read_text()
    assert TIKTOK in _hrefs(week, "View original")
    sentence = build.evidence_sentence(build.EVIDENCE["fancy-cafe"])
    assert "Know Your Meme explainer" in week
    assert "<summary>Sources &amp; details</summary>" in today
    assert 'class="zone zone-lead"' in today and 'class="zone zone-hist"' in today
    assert 'class="zone zone-by"' in today and 'class="zone zone-src"' in today
    assert 'class="zone zone-more"' in today
    assert sentence in week and "11.1M" not in week
    assert "AI-generated video" in week
    assert "AI-generated video" not in today
    # The page stamp is the memes.json build time, not an evidence observation.
    assert f'datetime="{build.ISO}"' in today
    assert "21:09" not in today

    assert TIKTOK in _hrefs(fancy, "View original")
    assert KYM not in _hrefs(fancy, "View original")
    assert "Know Your Meme explainer" in fancy
    assert "AI-generated" in fancy
    assert "comedy skit (and its AI remakes)" not in fancy
    assert "SKIT SPAWNS" not in today and "Skit Spawns" not in today
    assert "SKIT SPAWNS" not in fancy and "SKIT SPAWNS" not in home
    assert "AI-Generated Cafe Seating Mix-up" in week
    assert "POV: Your First Time in a Fancy Cafe" in week
    assert "AI-Generated Cafe Seating Mix-up" not in today
    assert "Sitting-on-the-table Skit Spawns" in nov7
    assert "AI-Generated Cafe Seating Mix-up" not in nov7
    assert "Me confidently sitting down" not in fancy
    assert "11.1M" not in fancy
    assert sentence in fancy
    assert "21:09" not in fancy
    assert "index.html" not in fancy
    assert "<summary>Sources &amp; details</summary>" in fancy
    # The AI-generated disclosure stays in the reading text, not only inside the disclosure.
    before, _, _rest = fancy.partition("<details")
    assert "AI-generated" in before

    assert "your country" not in cite
    assert "How to use it" not in cite
    assert XPOST in _hrefs(cite, "View credited post")
    assert "View original" not in cite
    assert "hasn’t been confirmed" in cite or "hasn't been confirmed" in cite
    assert "snow-leopard-paws-at-you" not in cite
    assert "heidi-32gb-ram" not in cite
    assert "sam-altman-ram" not in cite

    # Frozen archive observations stay on the counts recorded that day.
    assert "10.9M" in nov5 and "11.6M" not in nov5
    assert "11.4M" in nov6 and "11.6M" not in nov6
    assert "11.1M views" in snap
    assert "11.1M" not in nov7
    assert "11.6M" in nov7
    live_count = build.chip_count(build.EVIDENCE["fancy-cafe"], TIKTOK).split()[0]
    if live_count != "11.6M":
        assert live_count not in nov7
    assert TIKTOK in _hrefs(nov5, "View original")

    assert "index.html" not in home
    assert 'href="./"' in home
    # Curated RAM family links remain.
    heidi = (ROOT / "meme" / "heidi-32gb-ram" / "index.html").read_text()
    assert "meme/sam-altman-ram/" in heidi

    import html as html_lib
    def title_text(page):
        return html_lib.unescape(re.search(r"<title>(.*?)</title>", page).group(1))
    def h1_text(page):
        return html_lib.unescape(re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S).group(1))
    def desc_text(page):
        return html_lib.unescape(re.search(r'<meta name="description" content="(.*?)"', page).group(1))

    assert "MEMESTAND" not in h1_text(home)
    assert "THE TOP MEMES TODAY" in h1_text(home)
    assert title_text(home) == "MemeStand — Daily Meme Report: Today's Top Memes, Ranked by Virality"
    assert not title_text(home).startswith("Top 10 Memes Today")
    assert title_text(today).startswith("Top 10 Memes Today (")
    assert "Trending Memes Right Now | MemeStand" in title_text(today)
    month = (ROOT / "best-memes-this-month" / "index.html").read_text()
    assert title_text(month).startswith("Best Memes of ")
    assert "Top 10 Memes This Month | MemeStand" in title_text(month)
    assert "November 2026" in title_text(month) or build.NOW.strftime("%B %Y") in title_text(month)
    assert 'href="trending-memes-this-week/"' in home
    assert "trending memes this week" in home
    assert "best memes of the month" in home
    about = (ROOT / "about.html").read_text()
    assert "older links keep working" not in about
    assert "trending-memes-this-week/" in about
    crack = title_text((ROOT / "meme" / "crack-a-monster" / "index.html").read_text())
    assert crack == "Crack a Monster Meme ('It's Not That Deep'): Meaning & Origin | MemeStand"
    telegram = title_text((ROOT / "meme" / "telegram-microsoft" / "index.html").read_text())
    assert telegram == "Telegram Bill Gates Microsoft Joke Meme: Meaning & Origin | MemeStand"
    assert "/" not in telegram.split("|")[0]
    newton = (ROOT / "meme" / "newton-fourth-law" / "index.html").read_text()
    assert title_text(newton) == "Newton's Fourth Law of Motion Meme: Meaning & Origin | MemeStand"
    assert desc_text(newton).lower().startswith('"if newton saw the way i be moving')
    assert title_text((ROOT / "meme" / "seatbelt-dog" / "index.html").read_text()) == "Seatbelt Dog Meme: Meaning & Origin | MemeStand"
    assert title_text((ROOT / "meme" / "me-instructing" / "index.html").read_text()) == "Me Instructing Meme (Bakery Pointing Clip): Meaning & Origin | MemeStand"
    assert title_text((ROOT / "meme" / "affleck-i-voted-smoking" / "index.html").read_text()) == "Ben Affleck 'I Voted' Smoking Update Meme: Meaning & Origin | MemeStand"
    assert title_text((ROOT / "meme" / "bounce-baby-boy" / "index.html").read_text()) == "Boys Go Always Bounce Back Meme (Bouncing Baby Boy): Meaning & Origin | MemeStand"
    assert title_text((ROOT / "meme" / "why-is-my-sister-named-lily" / "index.html").read_text()) == "Why Is My Sister Named Lily Meme: Meaning & Origin | MemeStand"
    cousins = (ROOT / "meme" / "little-cousins-hippo-and-alligator" / "index.html").read_text()
    assert title_text(cousins) == "What My Little Cousins Do When They See Me Meme (Hippo & Alligator) | MemeStand"
    assert desc_text(cousins).lower().startswith('"what my little cousins do when they see me')
    assert title_text((ROOT / "meme" / "people-my-age-pregnancy-tests" / "index.html").read_text()) == "People My Age Buying Pregnancy Tests Meme: Meaning & Origin | MemeStand"
    regret = (ROOT / "meme" / "regretamine" / "index.html").read_text()
    assert "March 1, 2021" in regret
    assert "November 1, 2026" in regret
    assert "brought the joke back" in regret
    assert "The Independent" in regret and "Newsweek" in regret and "News18" in regret
    assert "origin_confirmed" not in regret
    assert "hasn’t been confirmed" in regret or "hasn't been confirmed" in regret
    assert "View original" not in regret
    kept = ROOT / "meme" / "little-void-creatures" / "index.html"
    assert kept.exists()
    assert "No saved daily report includes this meme right now." in kept.read_text()
    assert not (ROOT / "meme" / "fortnite-pirate-shop-token").exists()
    sm = (ROOT / "sitemap.xml").read_text()
    assert "<loc>https://memestand.com/meme/newton-fourth-law/</loc><lastmod>2026-11-09T14:17:26-08:00</lastmod>" in sm
    assert "<loc>https://memestand.com/meme/little-void-creatures/</loc><lastmod>2026-11-07T23:13:29-08:00</lastmod>" in sm
    assert "<loc>https://memestand.com/meme/seatbelt-dog/</loc><lastmod>2026-11-08T06:16:07-08:00</lastmod>" in sm


def test_search_console_file_is_exact_and_restored_by_build():
    path = ROOT / "google327e53c932d0bf40.html"
    path.write_bytes(b"<html>wrapped</html>\n")
    build.build_search_console()
    assert path.read_bytes() == b"google-site-verification: google327e53c932d0bf40.html"
    assert b"cloudflareinsights" not in path.read_bytes()
    assert b"<" not in path.read_bytes()
    path.unlink()
    build.build_search_console()
    assert path.read_bytes() == b"google-site-verification: google327e53c932d0bf40.html"


def main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"{len(fns)} tests passed")


if __name__ == "__main__":
    main()
