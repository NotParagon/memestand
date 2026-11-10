#!/usr/bin/env python3
"""Generate favicon.svg/.ico, apple-touch-icon.png and og-default.png from one M.

The mark is the IBM Plex Mono Bold "M": a white tile, a black border, a red M,
and three short bars under the M (red, blue, green). favicon.svg is that mark,
and the favicon, apple-touch icon, header, and share image all use it.

The font is OFL and is not committed. Set MEMESTAND_PLEX or pass a path.
Raster copies are rendered from the SVG (cairosvg) so they cannot drift.
"""
import io, os, pathlib, sys
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
BLUE = "#1a33cc"
GREEN = "#1a9933"
# Ink box of the M on the 180px apple-touch icon this file originally wrote.
# Scaled into the 64 viewBox so the outline sits where the raster M sits.
INK_180 = (56, 53, 122, 142)
# Inner edge of the 4-unit stroke on the 64 viewBox.
INNER_TOP, INNER_BOT = 4.0, 60.0


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


def mark_geometry(bounds):
    """Black frame and red M stay put horizontally. The M shifts up just enough
    that it and the three bars share the padding inside the frame.

    Each bar is 1/12 of the M's height. Together they span the M, with a small
    gap between bars and a similar gap under the letter.
    """
    x0, y0, x1, y1 = bounds
    s = 64 / 180
    left, top, right, bottom = (v * s for v in INK_180)
    scale = ((right - left) / (x1 - x0) + (bottom - top) / (y1 - y0)) / 2
    tx = left - x0 * scale
    ty = top + y1 * scale
    # Match the transform that is written into the SVG, then measure the ink.
    scale = float(f"{scale:.5f}")
    tx = float(f"{tx:.2f}")
    ty = float(f"{ty:.2f}")
    ink_left = tx + scale * x0
    ink_right = tx + scale * x1
    ink_top = ty - scale * y1
    ink_bottom = ty - scale * y0
    m_w = ink_right - ink_left
    m_h = ink_bottom - ink_top
    bar_h = m_h / 12
    gap_y = bar_h * 1.2
    gap_x = m_w * 0.06
    bar_w = (m_w - 2 * gap_x) / 3
    content_h = m_h + gap_y + bar_h
    pad = (INNER_BOT - INNER_TOP - content_h) / 2
    if pad < 2:
        sys.exit("bars do not fit inside the frame")
    new_top = INNER_TOP + pad
    ty -= ink_top - new_top
    bar_top = new_top + m_h + gap_y
    bars = []
    x = ink_left
    for color in (RED, BLUE, GREEN):
        bars.append((x, bar_top, bar_w, bar_h, color))
        x += bar_w + gap_x
    return scale, tx, ty, bars


def write_svg(path_d, bounds):
    scale, tx, ty, bars = mark_geometry(bounds)
    rects = "".join(
        f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="{color}"/>'
        for x, y, w, h, color in bars
    )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<rect width="64" height="64" fill="#fff"/>'
        '<rect x="2" y="2" width="60" height="60" fill="none" stroke="#000" stroke-width="4"/>'
        f'<path fill="{RED}" transform="matrix({scale:.5f} 0 0 {-scale:.5f} {tx:.2f} {ty:.2f})" d="{path_d}"/>'
        f"{rects}</svg>\n"
    )
    (ROOT / "favicon.svg").write_text(svg)
    return svg


def render_svg(svg, size):
    from cairosvg import svg2png
    png = svg2png(bytestring=svg.encode(), output_width=size, output_height=size)
    im = Image.open(io.BytesIO(png)).convert("RGBA")
    out = Image.new("RGB", im.size, "white")
    out.paste(im, mask=im.split()[-1])
    return out


def save_ico(svg):
    # The largest image has to be first. Pillow drops any size bigger than it.
    sizes = (48, 32, 16)
    images = [render_svg(svg, size) for size in sizes]
    images[0].save(
        ROOT / "favicon.ico",
        format="ICO",
        sizes=[(size, size) for size in sizes],
        append_images=images[1:],
    )


def write_og(font_file, tile):
    """Replace the mark tile on the share image. Redrawing the whole card
    re-rasterizes MEMESTAND, and this font does not match those pixels."""
    tile_size, gap, top = 132, 28, 168
    if tile.size != (tile_size, tile_size):
        tile = tile.resize((tile_size, tile_size), Image.Resampling.LANCZOS)
    dest = ROOT / "og-default.png"
    bold = ImageFont.truetype(font_file, 112)
    word = "MEMESTAND"
    existed = dest.is_file()
    if existed:
        og = Image.open(dest).convert("RGB")
    else:
        og = Image.new("RGB", (1200, 630), "white")
        d = ImageDraw.Draw(og)
        d.rectangle([20, 20, 1179, 609], outline="black", width=6)
        d.text((600, 400), "TOP 10 MEMES TODAY / THIS WEEK / THIS MONTH",
               font=ImageFont.truetype(font_file, 36), fill=RED, anchor="mm")
        d.text((600, 480), "THE DAILY MEME REPORT -- MEMESTAND.COM",
               font=ImageFont.truetype(font_file, 30), fill="black", anchor="mm")
    word_w = ImageDraw.Draw(og).textbbox((0, 0), word, font=bold)[2]
    left = int((og.size[0] - (tile_size + gap + word_w)) / 2)
    if not existed:
        ImageDraw.Draw(og).text(
            (left + tile_size + gap, top + tile_size / 2), word, font=bold, fill="black", anchor="lm")
    og.paste(tile, (left, top))
    og.save(dest, optimize=True)


def main():
    src = font_path()
    font = TTFont(src)
    raw, bounds = m_path(font)
    svg = write_svg(round_path(raw), bounds)
    save_ico(svg)
    render_svg(svg, 180).save(ROOT / "apple-touch-icon.png")
    write_og(src, render_svg(svg, 132))
    print("icons written from", src)


if __name__ == "__main__":
    main()
