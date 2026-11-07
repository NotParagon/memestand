"""Owner-approved attributed post cards.

data/post_cards.json maps a canonical meme slug (and its candidate ids) to a file
under images/post-cards/. The picture is a self-rendered card of a public post:
avatar, handle, and the full post text. It is not a screenshot of X and it is
not a third-party photo.

image_policy "none" still means "do not fetch a photo" for any meme that is not
listed in that file. A listed card is used only when the meme has no local or
hotlinked image of its own.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "data" / "post_cards.json"

_CACHE = None

def load():
    doc = json.loads(DOC.read_text())
    by = {}
    for slug, ent in doc["cards"].items():
        row = dict(ent)
        row["slug"] = slug
        by[slug] = row
        for i in ent.get("ids") or []:
            by[i] = row
    return by

def cards():
    global _CACHE
    if _CACHE is None:
        _CACHE = load()
    return _CACHE

def entry_for(key):
    if not key:
        return None
    ent = cards().get(key)
    if not ent:
        return None
    if not (ROOT / ent["file"]).is_file():
        return None
    return ent

def file_for(key):
    ent = entry_for(key)
    return ent["file"] if ent else None

def local_image(candidate, fetched_local, hotlink):
    """Image path to store on a ranked row. A mapped card fills in only when there is no photo."""
    if fetched_local or hotlink:
        return fetched_local
    return file_for(candidate.get("id"))

def is_post_card_path(path):
    return bool(path) and str(path).startswith("images/post-cards/")

def displayed_as_post_card(image, image_url, image_kind, meme_id):
    """True when the picture on the page is an attributed post card, including after rank.py stores its path."""
    if image_url:
        return False
    if is_post_card_path(image) or image_kind == "post_card":
        return True
    if image:
        return False
    return file_for(meme_id) is not None
