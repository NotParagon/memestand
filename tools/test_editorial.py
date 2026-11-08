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
    assert "11.6M views" in sentence
    assert "1.5M likes" in sentence
    assert "observed 2026-11-07" in sentence
    assert "11.1M" not in sentence
    assert "21:09" not in sentence
    assert "6AM" not in sentence
    # The same TikTok URL contributes the same count to the chip and the sentence.
    assert build.chip_count(ev, TIKTOK) == "11.6M views"
    assert "11.6M views" in sentence
    # Know Your Meme's page-view field has no checked clock, so it must not borrow the page build time.
    assert "no separate observation time on file" in sentence
    stale = {"id": "fancy-cafe", "notes": "TikTok @leehoustonx 11.1M views (Nov 6 6AM PT)."}
    assert "11.6M" in build.why_text(stale, True)
    assert build.why_text(stale, False).startswith("TikTok @leehoustonx 11.1M")


def test_archive_labels_are_not_rewritten_from_later_evidence():
    meme = {"id": "fancy-cafe", "also": [{"name": "TikTok / @leehoustonx (10.9M views)", "url": TIKTOK}]}
    assert build.synced_also_name(meme, meme["also"][0], False) == "TikTok / @leehoustonx (10.9M views)"
    assert build.synced_also_name(meme, meme["also"][0], True) == "TikTok / @leehoustonx (11.6M views)"


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


def test_home_links_do_not_use_index_html():
    assert build.home_href("") == "./"
    assert build.home_href("../../") == "../../"
    assert "index.html" not in build.mast("../../", "TAG", h1=False)
    assert "index.html" not in build.footer("../../")
    assert 'href="./"' in build.footer("")


def _hrefs(html, label):
    return re.findall(rf'<a href="([^"]+)"[^>]*>{label}</a>', html)


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
    assert TIKTOK in originals
    assert "Know Your Meme explainer" in today
    assert "11.6M views" in today and "observed 2026-11-07" in today
    assert "11.1M" not in today
    assert 'datetime="2026-11-07T21:09:00-08:00"' in today

    assert TIKTOK in _hrefs(fancy, "View original")
    assert KYM not in _hrefs(fancy, "View original")
    assert "Know Your Meme explainer" in fancy
    assert "AI-generated" in fancy
    assert "comedy skit (and its AI remakes)" not in fancy
    assert "SKIT SPAWNS" not in today and "SKIT SPAWNS" not in fancy and "SKIT SPAWNS" not in home
    assert "AI-GENERATED CAFE SEATING MIX-UP" in today
    assert "SKIT SPAWNS" in nov7
    assert "Me confidently sitting down" not in fancy
    assert "11.1M" not in fancy
    assert "11.6M views" in fancy and "observed 2026-11-07" in fancy
    assert "21:09" not in fancy
    assert "index.html" not in fancy

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
    assert TIKTOK in _hrefs(nov5, "View original")

    assert "index.html" not in home
    assert 'href="./"' in home
    # Curated RAM family links remain.
    heidi = (ROOT / "meme" / "heidi-32gb-ram" / "index.html").read_text()
    assert "meme/sam-altman-ram/" in heidi


def main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"{len(fns)} tests passed")


if __name__ == "__main__":
    main()
