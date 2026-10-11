"""Layout A (team rows with small logos) and the text-only fallback.

┌────────────────────────────────────────────────────────────────┐
│[logo] ABBR •                                              27   │  rows 0-11
│[logo] ABBR                                                24   │  rows 13-24
│Q3 4:12                                                   3&7   │  rows 26-31
└────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from PIL import Image

from ..models import Competitor, Game
from .base import (
    DETAIL_COLOR,
    LEAGUE_COLOR,
    NO_HIGHLIGHT,
    Highlight,
    RenderContext,
    blank,
    draw_dot,
    draw_right,
    draw_team_mark,
    fit_font,
    font,
    has_possession,
    league_label,
    possession_color,
    score_colors,
    score_text,
    status_color,
    team_rgb,
)

ROW_TOPS = (0, 13)
ROW_H = 12
LOGO_BOX = 12
STATUS_Y = 26

ABBR_FONTS = ("7x13B", "6x10", "5x8", "5x7", "4x6")
SCORE_FONTS = ("7x13B", "6x13B", "6x10", "5x8")


def _row(
    img: Image.Image,
    game: Game,
    c: Competitor,
    top: int,
    ctx: RenderContext,
    score_color,
    logos: bool,
    blink_visible: bool,
) -> None:
    x = 0
    if logos:
        had_logo = ctx.logo(game, c.team, LOGO_BOX) is not None
        if had_logo:
            draw_team_mark(
                img, game, c.team, (0, top, LOGO_BOX, top + ROW_H), ctx, visible=blink_visible
            )
            x = LOGO_BOX + 2
    score = score_text(c, game)
    sf = fit_font(score or "0", 22, SCORE_FONTS)
    score_left = 64 - sf.text_width(score) if score else 64
    # Rank (college) in small dim digits before the abbreviation, if it fits.
    if c.rank:
        tf = font("tom-thumb")
        rank = str(c.rank)
        tf.draw_cap(img, x, top + (ROW_H - tf.cap_height) // 2, rank, LEAGUE_COLOR)
        x += tf.text_width(rank) + 1
    room = score_left - x - 4
    af = fit_font(c.team.abbr, room, ABBR_FONTS)
    ay = top + (ROW_H - af.cap_height) // 2
    af.draw_cap(img, x, ay, c.team.abbr, team_rgb(c.team))
    if score:
        draw_right(img, sf, 63, top + (ROW_H - sf.cap_height) // 2, score, score_color)
    if has_possession(game, c, ctx):
        _, right = af.ink_bounds(c.team.abbr)
        dx = x + right + 2
        if dx + 2 < score_left - 1:
            draw_dot(img, dx, top + ROW_H // 2 - 1, possession_color(game))


def _status_row(img: Image.Image, game: Game, ctx: RenderContext) -> None:
    st = ctx.status(game)
    f = font("5x7")
    f.draw_cap(img, 0, STATUS_Y, st.line, status_color(game))
    used = f.text_width(st.line)
    right_text, color = "", LEAGUE_COLOR
    if game.state == "in" and st.detail and ctx.show_situation:
        right_text, color = st.detail, DETAIL_COLOR
    elif game.state != "in":
        right_text = league_label(game)
    if right_text:
        rf = fit_font(right_text, 64 - used - 3, ("5x7", "4x6", "tom-thumb"))
        if rf.text_width(right_text) <= 64 - used - 3:
            draw_right(img, rf, 63, STATUS_Y + (f.cap_height - rf.cap_height), right_text, color)


def render_rows(
    game: Game, ctx: RenderContext, hl: Highlight = NO_HIGHLIGHT, logos: bool = True
) -> Image.Image:
    img = blank()
    away_c, home_c = score_colors(game, hl)
    for c, top, color, side in (
        (game.away, ROW_TOPS[0], away_c, "away"),
        (game.home, ROW_TOPS[1], home_c, "home"),
    ):
        visible = not (hl.side == side and not hl.on)
        _row(img, game, c, top, ctx, color, logos, visible)
    _status_row(img, game, ctx)
    return img


def render_a(game: Game, ctx: RenderContext, hl: Highlight = NO_HIGHLIGHT) -> Image.Image:
    return render_rows(game, ctx, hl, logos=True)


def render_text(game: Game, ctx: RenderContext, hl: Highlight = NO_HIGHLIGHT) -> Image.Image:
    img = render_rows(game, ctx, hl, logos=False)
    # In text mode the "flash" blinks the scoring team's abbreviation instead.
    if hl.side and not hl.on:
        top = ROW_TOPS[0] if hl.side == "away" else ROW_TOPS[1]
        img.paste((0, 0, 0), (0, top, 36, top + ROW_H))
    return img
