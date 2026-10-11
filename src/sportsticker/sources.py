"""Scoreboard data sources: live ESPN, recorded fixtures, and a live-action simulator.

A Source returns the raw scoreboard JSON for one league. The poller never polls
a source faster than its `min_interval` (and never faster than `hard_min_interval`
if the source declares one, which LiveSource does to protect ESPN).
"""

from __future__ import annotations

import copy
import json
import logging
import math
import random
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import requests

from . import espn
from .models import League

log = logging.getLogger(__name__)

LIVE_MIN_INTERVAL = 30.0


class Source(Protocol):
    min_interval: float

    def fetch(self, league: League) -> dict: ...


class LiveSource:
    """Real ESPN scoreboards."""

    min_interval: float = LIVE_MIN_INTERVAL
    hard_min_interval: float = LIVE_MIN_INTERVAL  # the poller may never go below this

    def __init__(self, timeout: float = 10.0, session: requests.Session | None = None) -> None:
        self.timeout = timeout
        self.session = session or requests.Session()

    def fetch(self, league: League) -> dict:
        return espn.fetch_scoreboard(league, self.session, self.timeout)

    def close(self) -> None:
        self.session.close()


class ReplaySource:
    """Reads {sport}_{league}.json files recorded by espn.save_fixtures."""

    min_interval: float = 2.0

    def __init__(self, fixture_dir: str | Path) -> None:
        self.fixture_dir = Path(fixture_dir)

    def fetch(self, league: League) -> dict:
        path = self.fixture_dir / f"{league.sport}_{league.league}.json"
        try:
            text = path.read_text()
        except FileNotFoundError:
            return {"events": []}
        return json.loads(text)


# ------------------------------------------------------------ simulation


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _mmss(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


# Per ESPN path-part sport/league: (periods, seconds per period, clock kind)
_CLOCK_RULES: dict[str, tuple[int, int]] = {
    "football/nfl": (4, 900),
    "football/college-football": (4, 900),
    "basketball/nba": (4, 720),
    "basketball/wnba": (4, 600),
    "basketball/mens-college-basketball": (2, 1200),
    "hockey/nhl": (3, 1200),
}


class _Sim:
    """Mutable live state for one fake game."""

    def __init__(self, league: League, rng: random.Random) -> None:
        self.sport = league.sport
        periods, length = _CLOCK_RULES.get(league.path, (4, 720))
        if league.sport == "soccer":
            periods, length = 2, 45 * 60
        if league.sport == "baseball":
            periods, length = 9, 2  # innings; length = half-innings per inning
        self.periods = periods
        self.length = length
        self.rng = rng
        total = periods * length
        self.elapsed = rng.uniform(0.1, 0.7) * total  # game-seconds (baseball: half-innings)
        self.ticks = 0
        self.finished = False
        self.scores = {"home": 0, "away": 0}
        self.possession: str = "home"
        # Warm up scores in proportion to elapsed time.
        for _ in range(int(self.elapsed / total * self._expected_scores())):
            self.scores[rng.choice(("home", "away"))] += self.increment()

    def _expected_scores(self) -> int:
        return {"football": 6, "basketball": 40, "hockey": 5, "soccer": 2, "baseball": 8}.get(
            self.sport, 20
        )

    def increment(self) -> int:
        if self.sport == "football":
            return self.rng.choice((3, 7, 7))
        if self.sport == "basketball":
            return self.rng.choice((1, 2, 2, 2, 3))
        return 1

    def advance(self) -> bool:
        """Advance one fetch; returns True if someone scored."""
        if self.finished:
            return False
        rng = self.rng
        self.ticks += 1
        if self.sport == "baseball":
            if self.ticks % 4 == 0:
                self.elapsed += 1
            over = self.elapsed >= self.periods * self.length
            if over and self.scores["home"] != self.scores["away"]:
                self.finished = True
                return False
            p_score = 0.12
        else:
            self.elapsed += rng.uniform(40, 100) if self.sport != "soccer" else rng.uniform(90, 180)
            total = self.periods * self.length
            if self.elapsed >= total:
                tied = self.scores["home"] == self.scores["away"]
                if tied and self.sport != "soccer":
                    side = rng.choice(("home", "away"))  # no ties outside soccer: sudden death
                    self.scores[side] += self.increment()
                    self.elapsed = total
                    self.finished = True
                    return True
                self.elapsed = total
                self.finished = True
                return False
            p_score = {"soccer": 0.08, "hockey": 0.15}.get(self.sport, 0.3)
        if self.sport == "football" and rng.random() < 0.3:
            self.possession = "away" if self.possession == "home" else "home"
        if rng.random() < p_score:
            self.scores[rng.choice(("home", "away"))] += self.increment()
            return True
        return False

    # -- presentation ------------------------------------------------------

    def period(self) -> int:
        if self.sport == "baseball":
            return min(int(self.elapsed) // 2 + 1, self.periods + 9)
        if self.sport == "soccer":
            return 1 if self.elapsed < 45 * 60 else 2
        return min(int(self.elapsed // self.length) + 1, self.periods)

    def clock_text(self) -> str:
        if self.sport == "baseball":
            return ""
        if self.sport == "soccer":
            return f"{int(self.elapsed // 60)}'"
        into = self.elapsed - (self.period() - 1) * self.length
        return _mmss(self.length - into)

    def detail(self) -> str:
        if self.finished:
            return "FT" if self.sport == "soccer" else "Final"
        if self.sport == "baseball":
            inning = self.period()
            return f"{'Top' if int(self.elapsed) % 2 == 0 else 'Bot'} {_ordinal(inning)}"
        if self.sport == "soccer":
            return self.clock_text()
        return f"{self.clock_text()} - {_ordinal(self.period())}"

    def clock_seconds(self) -> float:
        if self.sport in ("baseball", "soccer"):
            return 0.0 if self.sport == "baseball" else self.elapsed
        into = self.elapsed - (self.period() - 1) * self.length
        return float(max(0, self.length - into))


def _event_sides(event: Any) -> tuple[dict, dict, dict] | None:
    """-> (competition, home competitor, away competitor), or None if malformed."""
    try:
        comp = event["competitions"][0]
        by_side = {c["homeAway"]: c for c in comp["competitors"]}
        return comp, by_side["home"], by_side["away"]
    except (KeyError, IndexError, TypeError):
        return None


class FakeLiveSource:
    """Wraps another source and makes about half of each league's games 'live'.

    The inner source is read once per league (so a wrapped LiveSource is not
    hammered); from then on this class keeps its own simulation and returns a
    mutated deep copy of the inner JSON on every fetch, so the normal parser
    path is exercised. Clocks advance and scores change on each fetch. When
    every simulated game in a league has finished, the simulation restarts so
    a demo never runs dry.
    """

    min_interval: float = 3.0

    def __init__(self, inner: Source, seed: int | None = None) -> None:
        self.inner = inner
        self._rng = random.Random(seed)
        self._lock = threading.Lock()
        self._base: dict[str, dict] = {}
        self._sims: dict[str, dict[str, _Sim]] = {}
        self._current: dict[str, dict] = {}

    def fetch(self, league: League) -> dict:
        with self._lock:
            if league.key not in self._base:
                data = self.inner.fetch(league)
                self._base[league.key] = copy.deepcopy(data) if isinstance(data, dict) else {}
                self._start(league)
            else:
                self._step(league)
            return copy.deepcopy(self._current[league.key])

    # -- internals ---------------------------------------------------------

    def _start(self, league: League) -> None:
        data = copy.deepcopy(self._base[league.key])
        events = data.get("events")
        sims: dict[str, _Sim] = {}
        if isinstance(events, list):
            valid = [e for e in events if _event_sides(e) is not None]
            count = math.ceil(len(valid) / 2) if len(valid) > 1 else len(valid)
            started = (datetime.now(UTC) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%MZ")
            for event in self._rng.sample(valid, count):
                sims[str(event.get("id"))] = _Sim(league, self._rng)
                # Pretend it kicked off an hour ago so it stays on today's board.
                event["date"] = started
                event["competitions"][0]["date"] = started
        self._sims[league.key] = sims
        self._current[league.key] = data
        self._apply(league, data)

    def _step(self, league: League) -> None:
        sims = self._sims[league.key]
        if sims and all(s.finished for s in sims.values()):
            self._start(league)
            return
        for sim in sims.values():
            sim.advance()
        self._apply(league, self._current[league.key])

    def _apply(self, league: League, data: dict) -> None:
        sims = self._sims[league.key]
        for event in data.get("events", []):
            sim = sims.get(str(event.get("id"))) if isinstance(event, dict) else None
            sides = _event_sides(event) if sim else None
            if sim is None or sides is None:
                continue
            comp, home, away = sides
            home["score"] = str(sim.scores["home"])
            away["score"] = str(sim.scores["away"])
            stype = {
                "id": "28" if sim.finished else "2",
                "name": "STATUS_FINAL" if sim.finished else "STATUS_IN_PROGRESS",
                "state": "post" if sim.finished else "in",
                "completed": sim.finished,
                "description": "Final" if sim.finished else "In Progress",
                "detail": sim.detail(),
                "shortDetail": sim.detail(),
            }
            status = {
                "clock": sim.clock_seconds(),
                "displayClock": sim.clock_text(),
                "period": sim.period(),
                "type": stype,
            }
            event["status"] = status
            comp["status"] = copy.deepcopy(status)
            if sim.sport == "football" and not sim.finished:
                comp["situation"] = self._situation(sim, home, away)
            else:
                comp.pop("situation", None)

    def _situation(self, sim: _Sim, home: dict, away: dict) -> dict:
        rng = random.Random(f"{sim.ticks}-{sim.scores['home']}-{sim.scores['away']}")
        side = home if sim.possession == "home" else away
        abbr = side.get("team", {}).get("abbreviation", "")
        down = rng.randint(1, 4)
        dist = rng.randint(1, 12)
        yard = rng.randint(1, 49)
        red = yard <= 20
        return {
            "down": down,
            "distance": dist,
            "downDistanceText": f"{_ordinal(down)} & {dist} at {abbr} {yard}",
            "shortDownDistanceText": f"{_ordinal(down)} & {dist}",
            "possessionText": f"{abbr} {yard}",
            "isRedZone": red,
            "possession": str(side.get("team", {}).get("id", side.get("id", ""))),
        }
