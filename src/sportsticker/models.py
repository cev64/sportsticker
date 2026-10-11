"""Plain data model shared by the data, logo, layout and app layers.

Everything downstream of the ESPN parser works with these objects only, never
with raw JSON, so a change in ESPN's payload is contained in espn.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

State = Literal["pre", "in", "post"]


@dataclass(frozen=True)
class League:
    key: str  # config key, e.g. "nfl"
    sport: str  # ESPN path part, e.g. "football"
    league: str  # ESPN path part, e.g. "nfl"
    label: str  # short display label, e.g. "NFL"
    college: bool = False  # shown with a "C" beside the sport glyph

    @property
    def path(self) -> str:
        return f"{self.sport}/{self.league}"


# Every league the app knows how to fetch. Config chooses which are enabled.
LEAGUES: dict[str, League] = {
    lg.key: lg
    for lg in (
        League("nfl", "football", "nfl", "NFL"),
        League("ncaaf", "football", "college-football", "NCAAF", college=True),
        League("nba", "basketball", "nba", "NBA"),
        League("ncaab", "basketball", "mens-college-basketball", "NCAAB", college=True),
        League("wnba", "basketball", "wnba", "WNBA"),
        League("mlb", "baseball", "mlb", "MLB"),
        League("nhl", "hockey", "nhl", "NHL"),
        League("epl", "soccer", "eng.1", "EPL"),
        League("mls", "soccer", "usa.1", "MLS"),
    )
}


@dataclass(frozen=True)
class Team:
    abbr: str  # e.g. "KC"; may be 2-5 chars
    name: str = ""  # e.g. "Chiefs" (shortDisplayName)
    color: str | None = None  # hex without '#', e.g. "e31837"
    alt_color: str | None = None
    logo_url: str | None = None
    logo_dark_url: str | None = None
    id: str = ""


@dataclass(frozen=True)
class Competitor:
    team: Team
    home: bool
    score: int | None = None  # None before the game / if missing
    rank: int | None = None  # college poll rank, if present


@dataclass(frozen=True)
class Situation:
    """Optional live football detail. Every field may be missing."""

    possession_team_id: str | None = None
    down_distance: str | None = None  # e.g. "3rd & 7"
    short_down_distance: str | None = None  # e.g. "3&7"
    red_zone: bool = False


@dataclass(frozen=True)
class Game:
    id: str
    league: str  # League.key
    state: State
    start: datetime  # timezone-aware (UTC from ESPN)
    away: Competitor
    home: Competitor
    short_detail: str = ""  # ESPN's status.type.shortDetail, e.g. "8:01 - 3rd"
    display_clock: str = ""  # e.g. "8:01"
    period: int = 0
    completed: bool = False
    situation: Situation | None = None
    extra: dict = field(default_factory=dict, compare=False, hash=False)

    def competitor_for(self, team_id: str) -> Competitor | None:
        for c in (self.away, self.home):
            if c.team.id and c.team.id == team_id:
                return c
        return None
