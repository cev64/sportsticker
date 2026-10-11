"""Make ESPN team colors readable on an LED panel.

ESPN colors are designed for white web pages: navy, black and dark green are
common and nearly invisible on LEDs. We pick the more visible of color and
alternateColor, then lift it to a minimum brightness while keeping its hue.
"""

from __future__ import annotations

import colorsys
from functools import lru_cache

RGB = tuple[int, int, int]

WHITE: RGB = (255, 255, 255)
BLACK: RGB = (0, 0, 0)
GRAY: RGB = (150, 150, 150)
DIM: RGB = (90, 90, 90)
YELLOW: RGB = (255, 200, 0)
RED: RGB = (255, 40, 30)
GREEN: RGB = (40, 220, 80)

# Lightness (HLS) floor for team colors, and saturation below which a color
# counts as "gray-ish" (black/white/silver) and loses to a colorful alternative.
MIN_LIGHTNESS = 0.45
MIN_VISIBLE = 0.22  # perceived luminance below this is "too dark" before lifting


def parse_hex(value: str | None) -> RGB | None:
    if not value or not isinstance(value, str):
        return None
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6:
        return None
    try:
        return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))
    except ValueError:
        return None


def luminance(c: RGB) -> float:
    """Perceived luminance 0..1 (Rec. 601 weights, good enough for LEDs)."""
    r, g, b = c
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def lift(c: RGB, min_lightness: float = MIN_LIGHTNESS) -> RGB:
    """Raise HLS lightness to at least `min_lightness`, keeping hue and saturation."""
    h, light, s = colorsys.rgb_to_hls(*(v / 255 for v in c))
    if light >= min_lightness:
        return c
    r, g, b = colorsys.hls_to_rgb(h, min_lightness, s)
    return (round(r * 255), round(g * 255), round(b * 255))


def _score(c: RGB) -> float:
    """How well a raw color reads on black: luminance plus a bonus for saturation."""
    _, light, s = colorsys.rgb_to_hls(*(v / 255 for v in c))
    return luminance(c) + 0.35 * s * min(1.0, light * 2)


@lru_cache(maxsize=512)
def team_color(primary: str | None, alternate: str | None) -> RGB:
    """Best LED color for a team: the more visible of primary/alternate, lifted.

    Falls back to white when neither color is usable (missing, or black/gray).
    """
    candidates = [c for c in (parse_hex(primary), parse_hex(alternate)) if c]
    if not candidates:
        return WHITE
    p = candidates[0]
    best = p
    if luminance(p) < MIN_VISIBLE and len(candidates) > 1:
        alt = candidates[1]
        if _score(alt) > _score(p):
            best = alt
    _, light, s = colorsys.rgb_to_hls(*(v / 255 for v in best))
    if s < 0.15:  # black / gray / white: no hue to lift, use white or light gray
        return WHITE if light > 0.6 or light < 0.25 else GRAY
    return lift(best)


def scale(c: RGB, factor: float) -> RGB:
    return (
        max(0, min(255, round(c[0] * factor))),
        max(0, min(255, round(c[1] * factor))),
        max(0, min(255, round(c[2] * factor))),
    )
