#!/usr/bin/env python3
"""Generate favicon.svg/.ico, apple-touch-icon.png and og-default.png from one M.

The mark is the IBM Plex Mono Bold "M" already used for apple-touch-icon.png:
a white tile, a black border, and a red M. favicon.svg uses that glyph's outline
so the header, the favicon, and the share image stay the same mark.

The font is OFL and is not committed. Set MEMESTAND_PLEX or pass a path.
"""
import os, pathlib, sys
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
CANDIDATES = [
    os.environ.get("MEMESTAND_PLEX") or "",
    "/usr/share/fonts/truetype/sand-box/google/IBM Plex Mono/IBMPlexMono-Bold.ttf",
    "/tmp/fonts/IBMPlexMono-Bold.otf",
    "/tmp/fonts/IBMPlexMono-Bold.ttf",
]
RED = "#cc0000"
# Ink box of the M on the 180px apple-touch icon this file originally wrote.
# Scaled into the 64 viewBox so the outline sits where the raster M sits.
INK_180 = (56, 53, 122, 142)


def font_path():
    for p in CANDIDATES:
        if p and pathlib.Path(p).is_file():
            return p
    sys.exit("IBM Plex Mono Bold not found. Set MEMESTAND_PLEX.")


def m_path(font):
    gs = font.getGlyphSet()
    glyph = gs["M"]
    bounds = BoundsPen(gs)
    glyph.draw(bounds)
    x0, y0, x1, y1 = bounds.bounds
    pen = SVGPathPen(gs)
    glyph.draw(pen)
    # One decimal keeps the file small and the curves smooth.
    raw = pen.getCommands()
    return raw, (x0, y0, x1, y1)


def round_path(commands):
    import re
    def repl(m):
        return f"{float(m.group()):.2f}".rstrip("0").rstrip(".")
    return re.sub(r"-?\d+\.\d+", repl, commands)


def write_svg(path_d, bounds):
    x0, y0, x1, y1 = bounds
    # Map the 180px ink box into the 64 viewBox used by the original favicon.svg.
    s = 64 / 180
    left, top, right, bottom = (v * s for v in INK_180)
    scale = ((right - left) / (x1 - x0) + (bottom - top) / (y1 - y0)) / 2
    tx = left - x0 * scale
    ty = top + y1 * scale
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<rect width="64" height="64" fill="#fff"/>'
        '<rect x="2" y="2" width="60" height="60" fill="none" stroke="#000" stroke-width="4"/>'
        f'<path fill="{RED}" transform="matrix({scale:.5f} 0 0 {-scale:.5f} {tx:.2f} {ty:.2f})" d="{path_d}"/>'
        "</svg>\n"
    )
    (ROOT / "favicon.svg").write_text(svg)


def icon(font_file, size):
    im = Image.new("RGB", (size, size), "white")
    d = ImageDraw.Draw(im)
    w = max(1, size // 16)
    d.rectangle([w // 2, w // 2, size - 1 - w // 2, size - 1 - w // 2], outline="black", width=w)
    f = ImageFont.truetype(font_file, int(size * 0.72))
    d.text((size / 2, size / 2 + size * 0.02), "M", font=f, fill=RED, anchor="mm")
    return im


def write_og(font_file, mark):
    og = Image.new("RGB", (1200, 630), "white")
    d = ImageDraw.Draw(og)
    d.rectangle([20, 20, 1179, 609], outline="black", width=6)
    bold = ImageFont.truetype(font_file, 112)
    word = "MEMESTAND"
    word_w = d.textbbox((0, 0), word, font=bold)[2]
    tile_size, gap = 132, 28
    tile = mark.resize((tile_size, tile_size), Image.Resampling.LANCZOS)
    total = tile_size + gap + word_w
    left = int((1200 - total) / 2)
    top = 168
    og.paste(tile, (left, top))
    d.text((left + tile_size + gap, top + tile_size / 2), word, font=bold, fill="black", anchor="lm")
    d.text((600, 400), "TOP 10 MEMES TODAY / THIS WEEK / THIS MONTH",
           font=ImageFont.truetype(font_file, 36), fill=RED, anchor="mm")
    d.text((600, 480), "THE DAILY MEME REPORT -- MEMESTAND.COM",
           font=ImageFont.truetype(font_file, 30), fill="black", anchor="mm")
    og.save(ROOT / "og-default.png", optimize=True)


def main():
    src = font_path()
    font = TTFont(src)
    raw, bounds = m_path(font)
    write_svg(round_path(raw), bounds)
    mark = icon(src, 256)
    mark.save(ROOT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    icon(src, 180).save(ROOT / "apple-touch-icon.png")
    write_og(src, icon(src, 180))
    print("icons written from", src)


if __name__ == "__main__":
    main()
