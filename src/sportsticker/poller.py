"""Background polling of scoreboards into a thread-safe ScoreState.

One daemon thread fetches every enabled league through a Source, parses and
filters the result, and publishes immutable snapshots for the render loop.
Failures never replace good data: the last successful games stay visible while
the error is recorded and the league backs off exponentially.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from . import espn
from .config import Config, PollingConfig, in_window
from .models import LEAGUES, Game
from .sources import Source

log = logging.getLogger(__name__)

IMMINENT = timedelta(minutes=15)  # a "pre" game this close to kickoff counts as live-ish
STALE_PRE = timedelta(hours=1)  # a "pre" game this far past kickoff is not "imminent" any more
COLLEGE_LEAGUES = ("ncaaf", "ncaab")
MAX_BACKOFF_EXPONENT = 20


@dataclass(frozen=True)
class ScoreState:
    """Read-only view of the poller's data. Treat the containers as immutable:
    a new ScoreState is built whenever something changes, so `version` (bumped
    whenever any league's games change) is a cheap change detector."""

    games: dict[str, list[Game]] = field(default_factory=dict)
    updated_at: dict[str, datetime] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    version: int = 0


def next_interval(
    games_by_league: dict[str, list[Game]], now_local: datetime, polling: PollingConfig
) -> float:
    """Seconds until the next poll, before clamping to the source's minimum.

    live_seconds when any shown game is in progress or a "pre" game starts
    within ~15 minutes; otherwise overnight_seconds inside the overnight window;
    otherwise idle_seconds.
    """
    now = now_local if now_local.tzinfo else now_local.replace(tzinfo=UTC)
    for games in games_by_league.values():
        for g in games:
            if g.state == "in":
                return float(polling.live_seconds)
            if g.state == "pre" and -STALE_PRE <= g.start - now <= IMMINENT:
                return float(polling.live_seconds)
    if in_window(now_local.time(), polling.overnight_start, polling.overnight_end):
        return float(polling.overnight_seconds)
    return float(polling.idle_seconds)


def _until_imminent(games_by_league: dict[str, list[Game]], now: datetime) -> float | None:
    """Seconds until the earliest not-yet-imminent "pre" game becomes imminent."""
    best: float | None = None
    for games in games_by_league.values():
        for g in games:
            if g.state != "pre":
                continue
            wait = (g.start - now - IMMINENT).total_seconds()
            if wait > 0 and (best is None or wait < best):
                best = wait
    return best


class Poller:
    def __init__(
        self,
        cfg: Config,
        source: Source,
        clock: Callable[[], float] = time.monotonic,
        now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.cfg = cfg
        self.source = source
        self._clock = clock
        self._now_fn = now_fn
        self._leagues = [k for k in cfg.leagues if k in LEAGUES]

        self._lock = threading.Lock()  # guards the published state below
        self._poll_lock = threading.Lock()  # one fetch cycle at a time
        self._games: dict[str, list[Game]] = {k: [] for k in self._leagues}
        self._updated: dict[str, datetime] = {}
        self._errors: dict[str, str] = {}
        self._version = 0
        self._snapshot: ScoreState | None = None

        self._failures: dict[str, int] = dict.fromkeys(self._leagues, 0)
        self._next_due: dict[str, float] = dict.fromkeys(self._leagues, self._clock())
        self.interval: float = float(cfg.polling.idle_seconds)  # last computed, for diagnostics

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------ public

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="sportsticker-poller", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)

    def snapshot(self) -> ScoreState:
        with self._lock:
            if self._snapshot is None:
                self._snapshot = ScoreState(
                    games={k: list(v) for k, v in self._games.items()},
                    updated_at=dict(self._updated),
                    errors=dict(self._errors),
                    version=self._version,
                )
            return self._snapshot

    def poll_now(self) -> ScoreState:
        """One synchronous cycle over every enabled league (ignores the schedule)."""
        self._cycle(self._leagues)
        return self.snapshot()

    def seconds_until_due(self, league_key: str) -> float:
        """Seconds until `league_key` is next polled by the background thread."""
        return max(0.0, self._next_due[league_key] - self._clock())

    @property
    def floor(self) -> float:
        """The fastest the source may be polled, in seconds."""
        src = self.source
        return max(
            float(getattr(src, "min_interval", 0) or 0),
            float(getattr(src, "hard_min_interval", 0) or 0),
        )

    # ---------------------------------------------------------- internals

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                now = self._clock()
                due = [k for k in self._leagues if self._next_due[k] <= now]
                if due:
                    self._cycle(due, interruptible=True)
                    now = self._clock()
                wait = min((self._next_due[k] - now for k in self._leagues), default=60.0)
                self._stop.wait(min(max(wait, 0.0), 60.0))
            except Exception:  # never let the thread die
                log.exception("poller loop error; continuing")
                self._stop.wait(5.0)

    def _fetch_league(self, key: str) -> list[Game]:
        raw = self.source.fetch(LEAGUES[key])
        events = raw.get("events") if isinstance(raw, dict) else None
        if not isinstance(events, list):
            raise ValueError("malformed scoreboard (no events list)")
        games = espn.parse_scoreboard(raw, key)
        if events and not games:
            raise ValueError(f"none of {len(events)} events could be parsed")
        now = self._now_fn()
        games = espn.filter_today(games, now, self.cfg.tz)
        if key in COLLEGE_LEAGUES:
            games = espn.college_filter(games, self.cfg.favorites.get(key, []))
        return games

    def _cycle(self, keys: list[str], interruptible: bool = False) -> None:
        with self._poll_lock:
            results: dict[str, list[Game] | Exception] = {}
            for key in keys:
                if interruptible and self._stop.is_set():
                    break
                try:
                    results[key] = self._fetch_league(key)
                except Exception as exc:  # a failing league must not block the others
                    results[key] = exc
            self._publish(results)

    def _publish(self, results: dict[str, list[Game] | Exception]) -> None:
        now = self._now_fn()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        t = self._clock()
        with self._lock:
            changed = False
            for key, res in results.items():
                if isinstance(res, Exception):
                    self._failures[key] = self._failures.get(key, 0) + 1
                    self._errors[key] = f"{type(res).__name__}: {res}"
                    changed = True
                else:
                    self._failures[key] = 0
                    if self._errors.pop(key, None) is not None:
                        changed = True
                    self._updated[key] = now
                    changed = True
                    if res != self._games.get(key):
                        self._games[key] = res
                        self._version += 1
            if changed:
                self._snapshot = None

            interval = self._compute_interval(now)
            self.interval = interval
            for key, res in results.items():
                if isinstance(res, Exception):
                    delay = self._backoff(key, interval)
                    log.warning(
                        "poll %s failed (%d in a row, retry in %.0fs): %s",
                        key,
                        self._failures[key],
                        delay,
                        self._errors[key],
                    )
                else:
                    delay = interval
                self._next_due[key] = t + delay

    def _compute_interval(self, now: datetime) -> float:
        polling = self.cfg.polling
        now_local = now.astimezone(self.cfg.tz)
        interval = next_interval(self._games, now_local, polling)
        soon = _until_imminent(self._games, now)
        if soon is not None:
            interval = min(interval, soon)  # wake up in time for an early kickoff
        return max(interval, self.floor)

    def _backoff(self, key: str, interval: float) -> float:
        failures = min(self._failures.get(key, 1), MAX_BACKOFF_EXPONENT)
        base = interval
        if key not in self._updated:  # never had good data: retry sooner than idle cadence
            base = max(min(interval, float(self.cfg.polling.live_seconds)), self.floor)
        delay = min(base * 2**failures, float(self.cfg.polling.max_backoff_seconds))
        return max(delay, base, self.floor)
