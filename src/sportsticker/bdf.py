"""Minimal BDF bitmap-font renderer that draws into Pillow images.

The rpi-rgb-led-matrix fonts are BDF files. Rendering them ourselves (instead of
graphics.DrawText on a canvas) means text is composed into the same Pillow frame
on the Pi, in the emulator and in snapshots, so all three are pixel-identical,
and rendered strings can be cached as part of a slide's static layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path

from PIL import Image

FONT_DIR = Path(__file__).parent / "fonts"


@dataclass(frozen=True)
class Glyph:
    width: int  # advance (DWIDTH)
    bbx_w: int
    bbx_h: int
    bbx_x: int
    bbx_y: int  # offset of the bitmap's bottom row from the baseline
    rows: tuple[int, ...]  # one int per bitmap row, MSB = leftmost pixel
    row_bits: int  # number of bits per row in `rows`


class BDFFont:
    def __init__(self, path: Path, max_codepoint: int = 0x2FF):
        self.name = path.stem
        self.glyphs: dict[int, Glyph] = {}
        self.ascent = 0
        self.descent = 0
        self._parse(path, max_codepoint)
        self.height = self.ascent + self.descent
        cap = self.glyphs.get(ord("0")) or self.glyphs.get(ord("X"))
        self.cap_height = cap.bbx_h + cap.bbx_y if cap else self.ascent

    def _parse(self, path: Path, max_cp: int) -> None:
        enc = -1
        dwidth = 0
        bbx = (0, 0, 0, 0)
        bitmap: list[int] | None = None
        font_bbx = (0, 0, 0, 0)
        for line in path.read_text(encoding="latin-1").splitlines():
            if bitmap is not None:
                if line.startswith("ENDCHAR"):
                    if 0 <= enc <= max_cp:
                        w, h, x, y = bbx
                        bits = ((w + 7) // 8) * 8
                        self.glyphs[enc] = Glyph(dwidth, w, h, x, y, tuple(bitmap), bits)
                    bitmap = None
                elif line:
                    bitmap.append(int(line, 16))
                continue
            key, _, rest = line.partition(" ")
            if key == "FONT_ASCENT":
                self.ascent = int(rest)
            elif key == "FONT_DESCENT":
                self.descent = int(rest)
            elif key == "FONTBOUNDINGBOX":
                font_bbx = tuple(int(v) for v in rest.split())
            elif key == "ENCODING":
                enc = int(rest.split()[0])
            elif key == "DWIDTH":
                dwidth = int(rest.split()[0])
            elif key == "BBX":
                bbx = tuple(int(v) for v in rest.split())
            elif key == "BITMAP":
                bitmap = []
        if not self.ascent and font_bbx[1]:
            self.ascent = font_bbx[1] + font_bbx[3]
            self.descent = -font_bbx[3]

    def glyph(self, ch: str) -> Glyph | None:
        return self.glyphs.get(ord(ch)) or self.glyphs.get(ord("?"))

    def text_width(self, text: str, spacing: int = 0) -> int:
        widths = [g.width for g in map(self.glyph, text) if g]
        return sum(widths) + spacing * max(0, len(widths) - 1)

    def ink_bounds(self, text: str, spacing: int = 0) -> tuple[int, int]:
        """(left, right) columns that actually contain pixels, for tight centering."""
        mask = self.render(text, spacing)
        box = mask.getbbox()
        return (box[0], box[2]) if box else (0, 0)

    def render(self, text: str, spacing: int = 0) -> Image.Image:
        """Render to an 'L' mask (255 = lit) of size (text_width, height)."""
        return _render(self, text, spacing)

    def draw(
        self,
        img: Image.Image,
        x: int,
        y: int,
        text: str,
        color: tuple[int, int, int],
        spacing: int = 0,
    ) -> int:
        """Draw text with its top-left (ascent line) at (x, y). Returns the width."""
        mask = self.render(text, spacing)
        if mask.width:
            img.paste(color, (x, y), mask)
        return mask.width


@lru_cache(maxsize=2048)
def _render(font: BDFFont, text: str, spacing: int) -> Image.Image:
    width = font.text_width(text, spacing)
    mask = Image.new("L", (max(width, 0), font.height), 0)
    if not width:
        return mask
    px = mask.load()
    pen = 0
    for ch in text:
        g = font.glyph(ch)
        if g is None:
            continue
        top = font.ascent - (g.bbx_y + g.bbx_h)
        for ry, row in enumerate(g.rows):
            yy = top + ry
            if not 0 <= yy < font.height:
                continue
            for rx in range(g.bbx_w):
                if row & (1 << (g.row_bits - 1 - rx)):
                    xx = pen + g.bbx_x + rx
                    if 0 <= xx < width:
                        px[xx, yy] = 255
        pen += g.width + spacing
    return mask


@cache
def load_font(name: str) -> BDFFont:
    """Load a font from the bundled fonts/ folder by stem, e.g. '5x7'. Cached."""
    path = FONT_DIR / f"{name}.bdf"
    if not path.exists():
        raise FileNotFoundError(f"font {name!r} not found in {FONT_DIR}")
    return BDFFont(path)
