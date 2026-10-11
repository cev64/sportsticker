"""Slide layouts. Each takes (game, ctx, highlight) and returns a 64x32 RGB image."""

from __future__ import annotations

from collections.abc import Callable

from PIL import Image

from ..models import Game
from .base import NO_HIGHLIGHT, Highlight, RenderContext
from .clock import render_clock
from .rows import render_a, render_text
from .split import render_b, render_c

LayoutFn = Callable[[Game, RenderContext, Highlight], Image.Image]

LAYOUTS: dict[str, LayoutFn] = {
    "a": render_a,
    "b": render_b,
    "c": render_c,
    "text": render_text,
}

# Logo bounding-box sizes each layout asks for (pre-scaled in the logo cache).
LOGO_SIZES: tuple[int, ...] = (12, 15, 21)


def render_game(
    layout: str, game: Game, ctx: RenderContext, hl: Highlight = NO_HIGHLIGHT
) -> Image.Image:
    return LAYOUTS[layout](game, ctx, hl)


__all__ = [
    "LAYOUTS",
    "LOGO_SIZES",
    "NO_HIGHLIGHT",
    "Highlight",
    "RenderContext",
    "render_clock",
    "render_game",
]
