"""Tiny pixel glyphs that stand in for the league name: one ball per sport.

Each glyph is 5 rows tall. College leagues get a 3x5 "C" to the left of the
ball. Seams and patches use dark colors instead of unlit pixels so every ball
still reads as a solid shape on the panel.
"""

from __future__ import annotations

from PIL import Image

from ..colors import RGB
from ..models import LEAGUES, Game

GLYPH_H = 5

PALETTE: dict[str, RGB] = {
    "B": (165, 82, 35),  # football leather
    "L": (230, 230, 230),  # football laces
    "O": (235, 115, 20),  # basketball
    "o": (110, 45, 5),  # basketball seams
    "W": (210, 210, 210),  # soccer ball, baseball
    "k": (55, 55, 60),  # soccer patches
    "R": (220, 40, 40),  # baseball stitches
    "S": (220, 180, 120),  # hockey stick
    "P": (160, 160, 170),  # hockey puck
    "C": (150, 150, 150),  # college "C"
}

GLYPHS: dict[str, tuple[str, ...]] = {
    "football": ("..BBB..", ".BLBLB.", "BBLLLBB", ".BLBLB.", "..BBB.."),
    "basketball": (".OOO.", "OOoOO", "ooooo", "OOoOO", ".OOO."),
    "soccer": (".WWW.", "WWkWW", "WkkkW", "WWkWW", ".WWW."),
    "baseball": (".WWW.", "RWWWR", "RWWWR", "RWWWR", ".WWW."),
    "hockey": ("......S", ".....S.", "....S..", "...S...", "SSS..PP"),
}

COLLEGE_C = ("CCC", "C..", "C..", "C..", "CCC")


def league_glyph(game: Game) -> tuple[Image.Image, Image.Image] | None:
    """(rgb, mask) sprite for the game's sport, with a "C" for college leagues.

    Returns None for a league or sport without a glyph (callers then fall back
    to the text label).
    """
    lg = LEAGUES.get(game.league)
    rows = GLYPHS.get(lg.sport) if lg else None
    if rows is None:
        return None
    if lg.college:
        width = max(len(r) for r in rows)
        rows = tuple(c + "." + r.ljust(width, ".") for c, r in zip(COLLEGE_C, rows, strict=True))
    w = max(len(r) for r in rows)
    rgb = Image.new("RGB", (w, GLYPH_H))
    mask = Image.new("L", (w, GLYPH_H), 0)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch != ".":
                rgb.putpixel((x, y), PALETTE[ch])
                mask.putpixel((x, y), 255)
    return rgb, mask
