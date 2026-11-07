#!/usr/bin/env python3
"""The four approved post cards resolve. An unlisted image_policy none meme does not."""
import sys
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from post_cards import file_for, local_image, entry_for, displayed_as_post_card

ROOT = Path(__file__).resolve().parent.parent
MAPPED = (
    "telegram-microsoft",
    "crack-a-monster",
    "britannica-mitochondria",
    "bounce-baby-boy",
)

def test_four_cards_resolve_and_affleck_does_not():
    for slug in MAPPED:
        ent = entry_for(slug)
        assert ent and ent["native_screenshot"] is False
        assert ent["kind"] == "self-rendered attributed post card"
        assert file_for(slug) == f"images/post-cards/{slug}.jpg"
        assert (ROOT / file_for(slug)).is_file()
    assert file_for("affleck-i-voted-smoking") is None
    assert entry_for("fancy-cafe") is None

def test_cards_are_square_and_do_not_keep_the_social_header():
    for slug in MAPPED:
        with Image.open(ROOT / file_for(slug)) as im:
            assert im.size == (1080, 1080), slug
            top = im.getpixel((20, 4))
            assert min(top) > 240, slug  # white card, not the black MemeStand bar
            assert ent_quote_present(slug)

def ent_quote_present(slug):
    ent = entry_for(slug)
    assert ent["quote"].strip()
    return True

def test_a_real_photo_wins_and_an_unlisted_text_post_stays_empty():
    assert local_image({"id": "fancy-cafe"}, "images/fancy-cafe.jpg", None) == "images/fancy-cafe.jpg"
    assert local_image({"id": "telegram-microsoft"}, None, None) == "images/post-cards/telegram-microsoft.jpg"
    assert local_image({"id": "telegram-microsoft"}, "images/telegram-microsoft.jpg", None) == "images/telegram-microsoft.jpg"
    assert local_image({"id": "affleck-i-voted-smoking"}, None, None) is None
    assert local_image({"id": "some-hotlink"}, None, "https://example.test/a.jpg") is None

def test_a_stored_card_path_still_counts_as_a_post_card():
    path = "images/post-cards/telegram-microsoft.jpg"
    assert displayed_as_post_card(path, None, "post_card", "telegram-microsoft")
    assert displayed_as_post_card(path, None, None, "telegram-microsoft")
    assert not displayed_as_post_card("images/fancy-cafe.jpg", None, None, "fancy-cafe")
    assert not displayed_as_post_card(None, "https://cdn.example/a.jpg", None, "telegram-microsoft")
    assert not displayed_as_post_card(None, None, None, "affleck-i-voted-smoking")

if __name__ == "__main__":
    test_four_cards_resolve_and_affleck_does_not()
    test_cards_are_square_and_do_not_keep_the_social_header()
    test_a_real_photo_wins_and_an_unlisted_text_post_stays_empty()
    test_a_stored_card_path_still_counts_as_a_post_card()
    print("ok")
