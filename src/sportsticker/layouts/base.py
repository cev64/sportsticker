"""Shared pieces for slide layouts: context, fonts, and drawing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from PIL import Image

from ..bdf import BDFFont, load_font
from ..colors import DIM, GRAY, RED, RGB, WHITE, YELLOW, team_color
from ..models import LEAGUES, Competitor, Game, Team
from ..status import Status, game_status
from .glyphs import league_glyph

W, H = 64, 32

SCORE_COLOR = WHITE
LOSER_COLOR = (120, 120, 120)
FLASH_COLOR = YELLOW
LIVE_COLOR = (255, 255, 255)
PRE_COLOR = (120, 170, 255)
FINAL_COLOR = (200, 200, 200)
DETAIL_COLOR = (230, 180, 40)
LEAGUE_COLOR = DIM
POSSESSION_COLOR = YELLOW
REDZONE_COLOR = RED


class LogoSource(Protocol):
    def get(self, league: str, abbr: str, size: int) -> Image.Image | None: ...


@dataclass(frozen=True)
class Highlight:
    """Score-change highlight: which side scored, and the current blink phase."""

    side: str | None = None  # "away" | "home" | None
    on: bool = True  # blink phase: logo visible when True


NO_HIGHLIGHT = Highlight()


@dataclass
class RenderContext:
    tz: ZoneInfo
    now: datetime
    logos: LogoSource | None = None
    show_situation: bool = True

    def status(self, game: Game) -> Status:
        return game_status(game, self.tz, self.now)

    def logo(self, game: Game, team: Team, size: int) -> Image.Image | None:
        if self.logos is None:
            return None
        try:
            return self.logos.get(game.league, team.abbr, size)
        except Exception:  # noqa: BLE001 - a logo problem must never break a frame
            return None


def font(name: str) -> BDFFont:
    return load_font(name)


def blank() -> Image.Image:
    return Image.new("RGB", (W, H), (0, 0, 0))


def team_rgb(team: Team) -> RGB:
    return team_color(team.color, team.alt_color)


def fit_font(text: str, max_width: int, names: tuple[str, ...]) -> BDFFont:
    """First font in `names` whose rendering of `text` fits max_width (else the last)."""
    for n in names:
        f = load_font(n)
        if f.text_width(text) <= max_width:
            return f
    return load_font(names[-1])


def ink_width(f: BDFFont, text: str) -> int:
    left, right = f.ink_bounds(text)
    return right - left


def draw_centered(img, f: BDFFont, cx: float, y: int, text: str, color: RGB) -> None:
    """Center text horizontally on cx using its ink bounds; y = top of capitals."""
    left, right = f.ink_bounds(text)
    x = round(cx - (right - left) / 2) - left
    f.draw_cap(img, x, y, text, color)


def draw_right(img, f: BDFFont, right_x: int, y: int, text: str, color: RGB) -> int:
    """Right-align text so its last lit column is right_x. Returns the left ink x."""
    left, right = f.ink_bounds(text)
    x = right_x + 1 - right
    f.draw_cap(img, x, y, text, color)
    return x + left


def score_text(c: Competitor, game: Game | None = None) -> str:
    """Score as text; blank before the game (ESPN sends 0-0 for scheduled games)."""
    if c.score is None or (game is not None and game.state == "pre"):
        return ""
    return str(c.score)


def score_colors(game: Game, hl: Highlight) -> tuple[RGB, RGB]:
    away, home = SCORE_COLOR, SCORE_COLOR
    if game.state == "post" and game.away.score is not None and game.home.score is not None:
        if game.away.score > game.home.score:
            home = LOSER_COLOR
        elif game.home.score > game.away.score:
            away = LOSER_COLOR
    if hl.side == "away":
        away = FLASH_COLOR
    elif hl.side == "home":
        home = FLASH_COLOR
    return away, home


def status_color(game: Game) -> RGB:
    return {"in": LIVE_COLOR, "pre": PRE_COLOR}.get(game.state, FINAL_COLOR)


def has_possession(game: Game, c: Competitor, ctx: RenderContext) -> bool:
    s = game.situation
    return bool(
        ctx.show_situation
        and game.state == "in"
        and s is not None
        and s.possession_team_id
        and c.team.id == s.possession_team_id
    )


def possession_color(game: Game) -> RGB:
    return REDZONE_COLOR if game.situation and game.situation.red_zone else POSSESSION_COLOR


def draw_dot(img: Image.Image, x: int, y: int, color: RGB, size: int = 2) -> None:
    img.paste(color, (x, y, x + size, y + size))


def paste_center(img: Image.Image, src: Image.Image, box: tuple[int, int, int, int]) -> None:
    """Paste src centered in box (x0, y0, x1, y1), exclusive right/bottom."""
    x0, y0, x1, y1 = box
    x = x0 + (x1 - x0 - src.width) // 2
    y = y0 + (y1 - y0 - src.height) // 2
    img.paste(src, (x, y))


def draw_team_mark(
    img: Image.Image,
    game: Game,
    team: Team,
    box: tuple[int, int, int, int],
    ctx: RenderContext,
    visible: bool = True,
) -> bool:
    """Logo centered in box, else the abbreviation in team color. Returns True if logo."""
    if not visible:
        return True
    x0, y0, x1, y1 = box
    size = min(x1 - x0, y1 - y0)
    logo = ctx.logo(game, team, size)
    if logo is not None:
        paste_center(img, logo, box)
        return True
    f = fit_font(team.abbr, x1 - x0, ("7x13B", "6x10", "5x8", "5x7", "4x6", "tom-thumb"))
    cy = y0 + (y1 - y0 - f.cap_height) // 2
    draw_centered(img, f, (x0 + x1 - 1) / 2, cy, team.abbr, team_rgb(team))
    return False


def league_label(game: Game) -> str:
    lg = LEAGUES.get(game.league)
    return lg.label if lg else game.league.upper()


def league_mark_width(game: Game) -> int:
    """Width of what draw_league_mark draws (glyph, else tom-thumb label)."""
    g = league_glyph(game)
    return g[0].width if g else ink_width(font("tom-thumb"), league_label(game))


def draw_league_mark(img: Image.Image, game: Game, x: int, y: int) -> None:
    """Sport glyph (or the league label if there is none) with its top-left at (x, y).

    Both are 5 rows tall, so they can swap without moving anything else.
    """
    g = league_glyph(game)
    if g:
        img.paste(g[0], (x, y), g[1])
    else:
        tf = font("tom-thumb")
        left, _ = tf.ink_bounds(league_label(game))
        tf.draw_cap(img, x - left, y, league_label(game), LEAGUE_COLOR)


def draw_league_mark_centered(img: Image.Image, game: Game, cx: float, y: int) -> None:
    draw_league_mark(img, game, round(cx - league_mark_width(game) / 2), y)


__all__ = [
    "DETAIL_COLOR",
    "GRAY",
    "LEAGUE_COLOR",
    "NO_HIGHLIGHT",
    "Highlight",
    "RenderContext",
    "W",
    "H",
]
