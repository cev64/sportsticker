"""Turn a small LED frame into images a human can inspect.

- led_view:  each pixel becomes a round dot on black, like the real panel.
- grid_view: each pixel becomes a square cell with grid lines and x/y rulers,
             so exact pixel positions can be read off.
"""

from __future__ import annotations

from functools import lru_cache

from PIL import Image, ImageDraw

from .bdf import load_font

UNLIT = (22, 22, 22)  # how an unlit LED looks (very dark gray dot)


@lru_cache(maxsize=8)
def _dot_mask(scale: int) -> Image.Image:
    """Antialiased round-dot mask for one LED cell, drawn at 4x then reduced."""
    big = scale * 4
    m = Image.new("L", (big, big), 0)
    pad = big * 0.12
    ImageDraw.Draw(m).ellipse((pad, pad, big - pad, big - pad), fill=255)
    return m.resize((scale, scale), Image.LANCZOS)


def led_view(frame: Image.Image, scale: int = 10, show_unlit: bool = True) -> Image.Image:
    """Render as round LEDs on black at `scale` px per LED."""
    frame = frame.convert("RGB")
    w, h = frame.size
    # Nearest-neighbour upscale gives the color of each cell; a tiled dot mask
    # cuts the round LED out of it. Unlit LEDs show as faint dots.
    colors = frame.resize((w * scale, h * scale), Image.NEAREST)
    if show_unlit:
        lit = frame.convert("L").point(lambda v: 255 if v else 0)
        lit = lit.resize(colors.size, Image.NEAREST)
        colors = Image.composite(colors, Image.new("RGB", colors.size, UNLIT), lit)
    tile = _dot_mask(scale)
    mask = Image.new("L", colors.size, 0)
    for y in range(h):
        for x in range(w):
            mask.paste(tile, (x * scale, y * scale))
    out = Image.new("RGB", colors.size, (0, 0, 0))
    out.paste(colors, (0, 0), mask)
    return out


def grid_view(frame: Image.Image, scale: int = 12, ruler: bool = True) -> Image.Image:
    """Square pixels with 1px grid lines, plus x/y coordinate rulers every 8 px."""
    frame = frame.convert("RGB")
    w, h = frame.size
    margin = 18 if ruler else 0
    body = frame.resize((w * scale, h * scale), Image.NEAREST)
    out = Image.new("RGB", (w * scale + margin + 1, h * scale + margin + 1), (0, 0, 0))
    out.paste(body, (margin, margin))
    d = ImageDraw.Draw(out)
    for x in range(w + 1):
        col = (90, 90, 90) if x % 8 == 0 else (40, 40, 40)
        d.line((margin + x * scale, margin, margin + x * scale, margin + h * scale), fill=col)
    for y in range(h + 1):
        col = (90, 90, 90) if y % 8 == 0 else (40, 40, 40)
        d.line((margin, margin + y * scale, margin + w * scale, margin + y * scale), fill=col)
    if ruler:
        f = load_font("4x6")
        for x in range(0, w, 8):
            f.draw(out, margin + x * scale + 2, 6, str(x), (160, 160, 160))
        for y in range(0, h, 8):
            f.draw(out, 1, margin + y * scale + 2, str(y), (160, 160, 160))
    return out


def side_by_side(images: list[Image.Image], gap: int = 16, bg=(0, 0, 0)) -> Image.Image:
    width = sum(i.width for i in images) + gap * (len(images) - 1)
    height = max(i.height for i in images)
    out = Image.new("RGB", (width, height), bg)
    x = 0
    for img in images:
        out.paste(img, (x, 0))
        x += img.width + gap
    return out
