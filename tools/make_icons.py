#!/usr/bin/env python3
"""One-time: generate favicon.svg/.ico, apple-touch-icon.png and og-default.png (static, committed)."""
import pathlib
from PIL import Image, ImageDraw, ImageFont
ROOT = pathlib.Path(__file__).resolve().parent.parent
BOLD = "/usr/share/fonts/truetype/sand-box/google/IBM Plex Mono/IBMPlexMono-Bold.ttf"

(ROOT / "favicon.svg").write_text(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" fill="#fff"/>'
    '<rect x="2" y="2" width="60" height="60" fill="none" stroke="#000" stroke-width="4"/>'
    '<text x="32" y="47" font-family="Courier New,Courier,monospace" font-weight="bold" font-size="44" '
    'text-anchor="middle" fill="#c00">M</text></svg>\n')

def icon(size):
    im = Image.new("RGB", (size, size), "white"); d = ImageDraw.Draw(im)
    w = max(1, size // 16); d.rectangle([w // 2, w // 2, size - 1 - w // 2, size - 1 - w // 2], outline="black", width=w)
    f = ImageFont.truetype(BOLD, int(size * 0.72))
    d.text((size / 2, size / 2 + size * 0.02), "M", font=f, fill="#cc0000", anchor="mm")
    return im

icon(256).save(ROOT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
icon(180).save(ROOT / "apple-touch-icon.png")

og = Image.new("RGB", (1200, 630), "white"); d = ImageDraw.Draw(og)
d.rectangle([20, 20, 1179, 609], outline="black", width=6)
d.text((600, 250), "MEMESTAND", font=ImageFont.truetype(BOLD, 150), fill="black", anchor="mm")
d.text((600, 380), "TOP 10 MEMES TODAY / THIS WEEK / THIS MONTH", font=ImageFont.truetype(BOLD, 40), fill="#cc0000", anchor="mm")
d.text((600, 470), "THE DAILY MEME REPORT -- MEMESTAND.COM", font=ImageFont.truetype(BOLD, 32), fill="black", anchor="mm")
og.save(ROOT / "og-default.png", optimize=True)
print("icons written")
