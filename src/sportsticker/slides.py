"""Which slides to show, in what order, for how long, and score-change detection."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .config import Config
from .models import Game

GROUP_RANK = {"in": 0, "pre": 1, "post": 2}


@dataclass(frozen=True)
class Slide:
    kind: str  # "game" | "clock"
    game: Game | None = None
    duration: float = 6.0
    favorite: bool = False

    @property
    def key(self) -> str:
        return f"game:{self.game.league}:{self.game.id}" if self.game else "clock"


def is_favorite_game(game: Game, cfg: Config) -> bool:
    return cfg.is_favorite(game.league, game.away.team.abbr) or cfg.is_favorite(
        game.league, game.home.team.abbr
    )


def order_games(games_by_league: dict[str, list[Game]], cfg: Config) -> list[Game]:
    """Live first, then upcoming by start time, then finals; favorites first in each."""
    league_rank = {k: i for i, k in enumerate(cfg.leagues)}
    games = [g for lg in cfg.leagues for g in games_by_league.get(lg, ())]

    def key(g: Game):
        group = GROUP_RANK.get(g.state, 1)
        fav = 0 if is_favorite_game(g, cfg) else 1
        lr = league_rank.get(g.league, 99)
        ts = g.start.timestamp()
        if group == 0:  # live: favorites, then league order, then earliest start
            return (group, fav, lr, ts, g.id)
        if group == 1:  # upcoming: favorites, then soonest
            return (group, fav, ts, lr, g.id)
        return (group, fav, lr, -ts, g.id)  # finals: favorites, league, most recent

    return sorted(games, key=key)


def build_playlist(games_by_league: dict[str, list[Game]], cfg: Config) -> list[Slide]:
    games = order_games(games_by_league, cfg)
    if not games:
        return [Slide("clock", duration=cfg.display.slide_seconds)]
    out = []
    for g in games:
        fav = is_favorite_game(g, cfg)
        dur = cfg.display.slide_seconds
        if fav and g.state == "in":
            dur = max(dur, cfg.display.favorite_live_seconds)
        out.append(Slide("game", g, dur, fav))
    return out


@dataclass(frozen=True)
class ScoreEvent:
    game_key: str
    side: str  # "away" | "home"
    points: int


class ScoreTracker:
    """Remembers scores per game and reports increases since the last update.

    The first time a game is seen, nothing is reported (no flash on startup).
    """

    def __init__(self) -> None:
        self._scores: dict[str, tuple[int | None, int | None]] = {}

    def update(self, games: Iterable[Game]) -> list[ScoreEvent]:
        events = []
        seen = set()
        for g in games:
            key = f"game:{g.league}:{g.id}"
            seen.add(key)
            now = (g.away.score, g.home.score)
            prev = self._scores.get(key)
            self._scores[key] = now
            if prev is None or g.state == "pre":
                continue
            for side, old, new in (("away", prev[0], now[0]), ("home", prev[1], now[1])):
                if old is not None and new is not None and new > old:
                    events.append(ScoreEvent(key, side, new - old))
        for gone in set(self._scores) - seen:
            del self._scores[gone]
        return events
