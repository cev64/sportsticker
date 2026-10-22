"""Layout B (big logos left/right) and layout C (logos with big scores).

B:                                       C:
 ┌──────┬────────┬──────┐                 ┌──────┬───────────┬───────┐
 │ away │   Q3   │ home │                 │ away │  27       │  Q3   │
 │ logo │  4:12  │ logo │                 ├──────┼───────────┤ 4:12  │
 │      │  3&7   │      │                 │ home │  24       │  3&7  │
 │  27  │  (ball)│  24  │                 └──────┴───────────┴───────┘
 └──────┴────────┴──────┘

B with team_labels (small initials, so every logo can be told apart):
  top     initials above a 21x15 logo        under   initials below it
  center  full-size logos; initials at the top of the middle column with the
          status stacked under them (no sport glyph)
  off     the plain layout above
"""

from __future__ import annotations

from PIL import Image

from ..colors import RGB, lift
from ..models import Game, Team
from .base import (
    DETAIL_COLOR,
    NO_HIGHLIGHT,
    Highlight,
    RenderContext,
    blank,
    draw_centered,
    draw_dot,
    draw_league_mark_centered,
    draw_right,
    draw_team_mark,
    fit_font,
    font,
    has_possession,
    possession_color,
    score_colors,
    score_text,
    status_color,
    team_rgb,
)

STACK_FONTS = ("5x7", "4x6", "tom-thumb")
LABEL_FONT = "tom-thumb"
# Initials are only 5 px tall, so they get more light than the big abbreviation.
LABEL_MIN_LIGHTNESS = 0.62
B_BOX = 21  # layout B logo column width (and logo box height without labels)
LABEL_LOGO_H = 15  # logo box height when the initials take a row


def _status_stack(
    img: Image.Image, game: Game, ctx: RenderContext, x0: int, x1: int, y0: int, y1: int
) -> None:
    """Status as up to three centered lines in the column [x0, x1)."""
    st = ctx.status(game)
    width = x1 - x0
    lines = [(st.period, status_color(game)), (st.clock, status_color(game))]
    if st.detail and ctx.show_situation and game.state == "in":
        lines.append((st.detail, DETAIL_COLOR))
    lines = [(t, c) for t, c in lines if t]
    fonts = [fit_font(t, width, STACK_FONTS) for t, _ in lines]
    gap = 2
    total = sum(f.cap_height for f in fonts) + gap * (len(lines) - 1)
    if total > y1 - y0:  # short column: smaller fonts, tighter lines
        fonts = [fit_font(t, width, STACK_FONTS[1:]) for t, _ in lines]
        gap = 1
        total = sum(f.cap_height for f in fonts) + gap * (len(lines) - 1)
    y = y0 + max(0, (y1 - y0 - total) // 2)
    cx = (x0 + x1 - 1) / 2
    for (text, color), f in zip(lines, fonts, strict=True):
        draw_centered(img, f, cx, y, text, color)
        y += f.cap_height + gap


def label_rgb(team: Team) -> RGB:
    return lift(team_rgb(team), LABEL_MIN_LIGHTNESS)


def draw_label(img: Image.Image, x: int, y: int, team: Team) -> int:
    """Team initials with their ink top-left at (x, y). Returns the ink width."""
    f = font(LABEL_FONT)
    left, right = f.ink_bounds(team.abbr)
    f.draw_cap(img, x - left, y, team.abbr, label_rgb(team))
    return right - left


def label_width(team: Team) -> int:
    left, right = font(LABEL_FONT).ink_bounds(team.abbr)
    return right - left


def render_b(game: Game, ctx: RenderContext, hl: Highlight = NO_HIGHLIGHT) -> Image.Image:
    img = blank()
    box_w = B_BOX
    mode = ctx.team_labels
    away_c, home_c = score_colors(game, hl)
    sides = ((game.away, 0, away_c, "away"), (game.home, 64 - box_w, home_c, "home"))
    # Initials join the logo only while there is a score: before the game the
    # abbreviation already sits under the logo, and without a logo the box
    # shows the abbreviation itself.
    labeled = {
        side: mode != "off"
        and bool(score_text(c, game))
        and ctx.logo(game, c.team, box_w) is not None
        for c, _, _, side in sides
    }
    center_tags = mode == "center" and any(labeled.values())
    for c, x0, color, side in sides:
        if labeled[side] and mode == "top":
            box = (x0, B_BOX - LABEL_LOGO_H, x0 + box_w, B_BOX)
            label_y = 0
        elif labeled[side] and mode == "under":
            box = (x0, 0, x0 + box_w, LABEL_LOGO_H)
            label_y = LABEL_LOGO_H + 1
        else:
            box = (x0, 0, x0 + box_w, B_BOX)
            label_y = None
        visible = not (hl.side == side and not hl.on)
        had_logo = draw_team_mark(img, game, c.team, box, ctx, visible=visible)
        cx = (box[0] + box[2] - 1) / 2
        if label_y is not None:
            draw_label(img, round(cx - label_width(c.team) / 2), label_y, c.team)
        score = score_text(c, game)
        score_ink = None  # (left, right, top, cap height) of the drawn score
        if score:
            f = fit_font(score, box_w, ("7x13B", "6x13B", "5x8"))
            draw_centered(img, f, cx, 22, score, color)
            left, right = f.ink_bounds(score)
            x = round(cx - (right - left) / 2)
            score_ink = (x, x + right - left, 22, f.cap_height)
        elif had_logo:  # before the game: show the abbreviation under the logo
            f = fit_font(c.team.abbr, box_w, ("6x10", "5x7", "4x6"))
            draw_centered(img, f, cx, 23, c.team.abbr, team_rgb(c.team))
        if has_possession(game, c, ctx):
            if score_ink:
                # Beside the score, on the side facing the middle of the panel.
                ink_l, ink_r, top, cap = score_ink
                dot_x = ink_r + 2 if side == "away" else ink_l - 4
                dot_y = top + cap // 2 - 1
            else:
                dot_x = box[2] + 1 if side == "away" else box[0] - 3
                dot_y = box[3] - 3
            draw_dot(img, dot_x, dot_y, possession_color(game))
    if center_tags:
        # Away initials flush left, home flush right one row lower, so long
        # abbreviations never collide; the status fills the column below.
        if labeled["away"]:
            draw_label(img, box_w + 2, 0, game.away.team)
        if labeled["home"]:
            draw_label(img, 64 - box_w - 2 - label_width(game.home.team), 6, game.home.team)
        _status_stack(img, game, ctx, box_w, 64 - box_w, 12, 32)
        return img
    _status_stack(img, game, ctx, box_w, 64 - box_w, 0, 21)
    draw_league_mark_centered(img, game, 31.5, 25)
    return img


def render_c(game: Game, ctx: RenderContext, hl: Highlight = NO_HIGHLIGHT) -> Image.Image:
    img = blank()
    logo_box = 15
    col_x = 44  # status column starts here
    away_c, home_c = score_colors(game, hl)
    rows = ((game.away, 0, away_c, "away"), (game.home, 16, home_c, "home"))
    score_room = col_x - (logo_box + 3) - 2
    scores = [score_text(c, game) for c, *_ in rows]
    longest = max(scores, key=len) or "0"
    sf = fit_font(longest, score_room, ("8x13B", "7x13B", "6x13B", "5x8"))
    for (c, top, color, side), score in zip(rows, scores, strict=True):
        visible = not (hl.side == side and not hl.on)
        draw_team_mark(img, game, c.team, (0, top, logo_box, top + logo_box), ctx, visible)
        x = logo_box + 3
        y = top + (logo_box - sf.cap_height) // 2
        if score:
            # Right-align scores to a shared edge so digits line up.
            draw_right(img, sf, col_x - 3, y, score, color)
        else:
            f = fit_font(c.team.abbr, score_room, ("6x10", "5x7", "4x6"))
            f.draw_cap(img, x, top + (logo_box - f.cap_height) // 2, c.team.abbr, team_rgb(c.team))
        if has_possession(game, c, ctx):
            draw_dot(img, logo_box + 1, top + logo_box // 2 - 1, possession_color(game))
    # thin divider and status column
    img.paste((40, 40, 40), (col_x - 1, 2, col_x, 30))
    _status_stack(img, game, ctx, col_x, 64, 0, 25)
    draw_league_mark_centered(img, game, (col_x + 63) / 2, 27)
    return img
