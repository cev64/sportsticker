"""Poller, interval rules and data sources. No network, no real sleeping."""

from __future__ import annotations

import copy
import dataclasses
import json
import re
import time
from datetime import UTC, datetime, timedelta
from datetime import time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from sportsticker import espn
from sportsticker.config import PollingConfig, parse_config
from sportsticker.models import LEAGUES, Competitor, Game, Team
from sportsticker.poller import Poller, ScoreState, next_interval
from sportsticker.sources import FakeLiveSource, LiveSource, ReplaySource

FIXTURES = Path(__file__).parent / "fixtures" / "2026-10-11-sun"
NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 11, 18, 0, tzinfo=UTC)  # Sunday 2 PM Eastern


def ny(h, m=0, day=11):
    return datetime(2026, 10, day, h, m, tzinfo=NY)


def make_cfg(leagues=("nfl",), favorites=None, **polling):
    raw = {
        "timezone": "America/New_York",
        "leagues": {k: True for k in leagues},
        "favorites": favorites or {},
        "polling": polling,
    }
    return parse_config(raw)


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def game(gid="g", state="pre", start=None, **kw):
    start = start or NOW
    return Game(
        id=gid,
        league="nfl",
        state=state,
        start=start,
        away=Competitor(Team(abbr="AWY"), False),
        home=Competitor(Team(abbr="HOM"), True),
        **kw,
    )


def raw_event(gid, start: datetime, state="pre"):
    return {
        "id": gid,
        "date": start.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ"),
        "status": {"type": {"state": state, "shortDetail": "x"}},
        "competitions": [
            {
                "competitors": [
                    {"homeAway": "home", "score": "0", "team": {"id": "1", "abbreviation": "HOM"}},
                    {"homeAway": "away", "score": "0", "team": {"id": "2", "abbreviation": "AWY"}},
                ]
            }
        ],
    }


class ScriptedSource:
    """Returns payloads (or raises exceptions) from per-league scripts."""

    def __init__(self, scripts, min_interval=2.0):
        self.scripts = {k: list(v) for k, v in scripts.items()}
        self.min_interval = min_interval
        self.calls: list[str] = []

    def fetch(self, league):
        self.calls.append(league.key)
        script = self.scripts[league.key]
        item = script.pop(0) if len(script) > 1 else script[0]
        if isinstance(item, Exception):
            raise item
        return copy.deepcopy(item)


def board(*events):
    return {"events": list(events)}


LIVE_BOARD = board(raw_event("1", NOW - timedelta(hours=1), "in"))
IDLE_BOARD = board(raw_event("1", NOW + timedelta(hours=5), "pre"))


# ------------------------------------------------------------- next_interval

POLLING = PollingConfig(
    live_seconds=30,
    idle_seconds=300,
    overnight_seconds=3600,
    overnight_start=dtime(1, 0),
    overnight_end=dtime(8, 0),
)


def test_next_interval_live_game():
    games = {"nfl": [game(state="in", start=ny(13))], "nba": []}
    assert next_interval(games, ny(14), POLLING) == 30
    assert next_interval(games, ny(3), POLLING) == 30  # live beats overnight


def test_next_interval_imminent_pre_game():
    soon = {"nfl": [game(state="pre", start=ny(14, 10))]}
    assert next_interval(soon, ny(14), POLLING) == 30
    assert next_interval(soon, ny(14, 0), POLLING) == 30
    edge = {"nfl": [game(state="pre", start=ny(14, 15))]}
    assert next_interval(edge, ny(14), POLLING) == 30
    far = {"nfl": [game(state="pre", start=ny(14, 16))]}
    assert next_interval(far, ny(14), POLLING) == 300
    just_late = {"nfl": [game(state="pre", start=ny(13, 50))]}  # ESPN still says pre
    assert next_interval(just_late, ny(14), POLLING) == 30
    stale = {"nfl": [game(state="pre", start=ny(9))]}
    assert next_interval(stale, ny(14), POLLING) == 300


def test_next_interval_idle_and_overnight():
    final = {"nfl": [game(state="post", start=ny(13))]}
    assert next_interval(final, ny(14), POLLING) == 300
    assert next_interval({}, ny(14), POLLING) == 300
    assert next_interval(final, ny(0, 59), POLLING) == 300
    assert next_interval(final, ny(1, 0), POLLING) == 3600
    assert next_interval(final, ny(7, 59), POLLING) == 3600
    assert next_interval(final, ny(8, 0), POLLING) == 300


def test_next_interval_overnight_window_wrapping_midnight():
    wrap = dataclasses.replace(POLLING, overnight_start=dtime(23, 0), overnight_end=dtime(6, 0))
    assert next_interval({}, ny(23, 30), wrap) == 3600
    assert next_interval({}, ny(5, 0), wrap) == 3600
    assert next_interval({}, ny(12, 0), wrap) == 300


def test_next_interval_naive_now_does_not_raise():
    games = {"nfl": [game(state="pre", start=NOW + timedelta(minutes=5))]}
    assert next_interval(games, datetime(2026, 10, 11, 18, 0), POLLING) == 30


# ------------------------------------------------------------- poll basics


def test_poll_now_with_replay_fixtures():
    cfg = make_cfg(["nfl", "nba", "nhl", "epl"])
    p = Poller(cfg, ReplaySource(FIXTURES), clock=Clock(), now_fn=lambda: NOW)
    assert p.snapshot().version == 0
    assert p.snapshot().games == {"nfl": [], "nba": [], "nhl": [], "epl": []}
    snap = p.poll_now()
    assert isinstance(snap, ScoreState)
    assert len(snap.games["nfl"]) == 13  # whole-week board trimmed to the ticker day
    assert {g.id for g in snap.games["nfl"]}.isdisjoint({"401872980", "401872994"})
    assert len(snap.games["nba"]) == 4  # the 10:00Z game is Sunday 6 AM Eastern: still today
    assert len(snap.games["nhl"]) == 3
    assert len(snap.games["epl"]) == 3
    assert snap.errors == {}
    assert set(snap.updated_at) == {"nfl", "nba", "nhl", "epl"}
    assert all(t == NOW for t in snap.updated_at.values())
    assert snap.version == 4


def test_version_bumps_only_on_change():
    clock = Clock()
    src = ScriptedSource({"nfl": [LIVE_BOARD, LIVE_BOARD, IDLE_BOARD]})
    p = Poller(make_cfg(), src, clock=clock, now_fn=lambda: NOW)
    v1 = p.poll_now().version
    assert v1 == 1
    s2 = p.poll_now()
    assert s2.version == v1  # identical data
    s3 = p.poll_now()
    assert s3.version == v1 + 1
    assert s3 is not s2


def test_snapshot_is_cached_and_frozen():
    p = Poller(make_cfg(), ScriptedSource({"nfl": [LIVE_BOARD]}), clock=Clock(), now_fn=lambda: NOW)
    p.poll_now()
    a = p.snapshot()
    assert p.snapshot() is a
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.version = 99  # type: ignore[misc]
    p.poll_now()
    assert p.snapshot() is not a  # updated_at moved
    assert p.snapshot().version == a.version


def test_college_filter_applied_with_favorites():
    now = datetime(2026, 10, 10, 18, 0, tzinfo=UTC)  # Saturday: the big college slate

    def run(favs):
        cfg = make_cfg(["ncaaf"], favorites={"ncaaf": favs})
        p = Poller(cfg, ReplaySource(FIXTURES), clock=Clock(), now_fn=lambda: now)
        return p.poll_now().games["ncaaf"]

    plain = run([])
    assert plain and all(any(c.rank for c in (g.away, g.home)) for g in plain)  # ranked games only
    plain_ids = {g.id for g in plain}
    unranked = next(
        g
        for g in espn.parse_scoreboard(
            json.loads((FIXTURES / "football_college-football.json").read_text()), "ncaaf"
        )
        if g.id not in plain_ids and espn.ticker_day(g.start, NY) == espn.ticker_day(now, NY)
    )
    with_fav = run([unranked.home.team.abbr.lower()])
    assert len(with_fav) == len(plain) + 1
    assert unranked.id in {g.id for g in with_fav}


def test_no_college_filter_for_pro_leagues():
    cfg = make_cfg(["nhl"])
    p = Poller(cfg, ReplaySource(FIXTURES), clock=Clock(), now_fn=lambda: NOW)
    assert len(p.poll_now().games["nhl"]) == 3  # no ranks, no favorites, still all shown


# ------------------------------------------------------------ error handling


def test_failure_keeps_last_good_data():
    src = ScriptedSource({"nfl": [LIVE_BOARD, RuntimeError("503 from ESPN")]})
    p = Poller(make_cfg(), src, clock=Clock(), now_fn=lambda: NOW)
    good = p.poll_now()
    assert len(good.games["nfl"]) == 1
    later = NOW + timedelta(minutes=1)
    p._now_fn = lambda: later
    bad = p.poll_now()
    assert bad.games["nfl"] == good.games["nfl"]
    assert bad.version == good.version
    assert bad.updated_at["nfl"] == NOW  # not refreshed by a failure
    assert "RuntimeError" in bad.errors["nfl"] and "503" in bad.errors["nfl"]


@pytest.mark.parametrize("payload", [{}, {"error": "oops"}, {"events": "nope"}, [], None, "<html>"])
def test_malformed_payload_is_an_error_not_empty_data(payload):
    src = ScriptedSource({"nfl": [LIVE_BOARD, payload]})
    p = Poller(make_cfg(), src, clock=Clock(), now_fn=lambda: NOW)
    p.poll_now()
    snap = p.poll_now()
    assert len(snap.games["nfl"]) == 1
    assert "nfl" in snap.errors


def test_unparseable_events_is_an_error():
    junk = board({"id": "1"}, {"foo": "bar"})
    src = ScriptedSource({"nfl": [LIVE_BOARD, junk]})
    p = Poller(make_cfg(), src, clock=Clock(), now_fn=lambda: NOW)
    p.poll_now()
    snap = p.poll_now()
    assert len(snap.games["nfl"]) == 1 and "nfl" in snap.errors


def test_legitimately_empty_board_replaces_games():
    src = ScriptedSource({"nfl": [LIVE_BOARD, board()]})
    p = Poller(make_cfg(), src, clock=Clock(), now_fn=lambda: NOW)
    p.poll_now()
    snap = p.poll_now()
    assert snap.games["nfl"] == [] and snap.errors == {}


def test_recovery_clears_error():
    src = ScriptedSource({"nfl": [ValueError("x"), LIVE_BOARD]})
    p = Poller(make_cfg(), src, clock=Clock(), now_fn=lambda: NOW)
    first = p.poll_now()
    assert "nfl" in first.errors and first.games["nfl"] == [] and "nfl" not in first.updated_at
    ok = p.poll_now()
    assert ok.errors == {} and len(ok.games["nfl"]) == 1 and ok.version == 1


def test_failing_league_does_not_block_others():
    src = ScriptedSource({"nfl": [ConnectionError("down")], "nba": [LIVE_BOARD]})
    p = Poller(make_cfg(["nfl", "nba"]), src, clock=Clock(), now_fn=lambda: NOW)
    snap = p.poll_now()
    assert src.calls == ["nfl", "nba"]
    assert "nfl" in snap.errors and "nba" not in snap.errors
    assert len(snap.games["nba"]) == 1


def test_backoff_doubles_caps_and_recovers():
    clock = Clock()
    src = ScriptedSource({"nfl": [LIVE_BOARD] + [OSError("x")] * 7 + [LIVE_BOARD]})
    p = Poller(make_cfg(max_backoff_seconds=900), src, clock=clock, now_fn=lambda: NOW)
    p.poll_now()
    assert p.seconds_until_due("nfl") == 30  # live game -> live_seconds
    delays = []
    for _ in range(7):
        p.poll_now()
        delays.append(p.seconds_until_due("nfl"))
    assert delays == [60, 120, 240, 480, 900, 900, 900]
    p.poll_now()  # script is on its last item: success
    assert p.snapshot().errors == {}
    assert p.seconds_until_due("nfl") == 30


def test_backoff_never_below_normal_interval():
    # idle cadence 300 s with a tiny max_backoff: a retry is never *faster* than normal
    cfg = make_cfg(max_backoff_seconds=30)
    src = ScriptedSource({"nfl": [IDLE_BOARD, OSError("x")]})
    p = Poller(cfg, src, clock=Clock(), now_fn=lambda: NOW)
    p.poll_now()
    assert p.seconds_until_due("nfl") == 300
    p.poll_now()
    assert p.seconds_until_due("nfl") == 300


def test_never_succeeded_league_retries_at_live_cadence():
    src = ScriptedSource({"nfl": [OSError("x")]})
    p = Poller(make_cfg(), src, clock=Clock(), now_fn=lambda: NOW)
    p.poll_now()
    assert p.seconds_until_due("nfl") == 60  # 30 * 2, not 300 * 2
    p.poll_now()
    assert p.seconds_until_due("nfl") == 120


def test_failure_logs_one_warning_line(caplog):
    src = ScriptedSource({"nfl": [OSError("kaput")]})
    p = Poller(make_cfg(), src, clock=Clock(), now_fn=lambda: NOW)
    with caplog.at_level("WARNING", logger="sportsticker.poller"):
        p.poll_now()
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1 and "kaput" in warnings[0].getMessage()
    assert warnings[0].exc_info is None  # no traceback spam


# ------------------------------------------------------------- scheduling


def test_idle_and_overnight_intervals_through_poller():
    src = ScriptedSource({"nfl": [IDLE_BOARD]})
    p = Poller(make_cfg(), src, clock=Clock(), now_fn=lambda: NOW)
    p.poll_now()
    assert p.seconds_until_due("nfl") == 300
    over_now = datetime(2026, 10, 11, 6, 0, tzinfo=UTC)  # 2 AM Eastern, game tonight
    far = board(raw_event("1", over_now + timedelta(hours=30), "pre"))
    p2 = Poller(make_cfg(), ScriptedSource({"nfl": [far]}), clock=Clock(), now_fn=lambda: over_now)
    p2.poll_now()
    assert p2.seconds_until_due("nfl") == 3600


def test_overnight_poll_wakes_in_time_for_early_kickoff():
    now = ny(6, 0).astimezone(UTC)
    early = board(raw_event("1", ny(6, 40).astimezone(UTC), "pre"))  # 6:40 AM Eastern kickoff
    p = Poller(make_cfg(), ScriptedSource({"nfl": [early]}), clock=Clock(), now_fn=lambda: now)
    p.poll_now()
    assert p.seconds_until_due("nfl") == pytest.approx(25 * 60)  # 6:25 = 15 min before kickoff


def test_source_min_interval_is_a_floor():
    src = ScriptedSource({"nfl": [LIVE_BOARD]}, min_interval=100)
    p = Poller(make_cfg(), src, clock=Clock(), now_fn=lambda: NOW)
    p.poll_now()
    assert p.seconds_until_due("nfl") == 100


class OfflineLive(LiveSource):
    """A LiveSource that never touches the network."""

    def fetch(self, league):
        return copy.deepcopy(LIVE_BOARD)


def test_live_source_floor_is_always_30():
    live = OfflineLive(timeout=1)
    assert live.min_interval == 30
    cfg = make_cfg()
    cfg.polling.live_seconds = 5  # bypass config validation on purpose
    p = Poller(cfg, live, clock=Clock(), now_fn=lambda: NOW)
    assert p.floor == 30
    p.poll_now()
    assert p.seconds_until_due("nfl") == 30
    live.min_interval = 1  # even a tampered min_interval cannot go below the hard floor
    p.poll_now()
    assert p.seconds_until_due("nfl") == 30


def test_replay_source_is_faster_than_live():
    r = ReplaySource(FIXTURES)
    assert r.min_interval == 2
    cfg = make_cfg()
    cfg.polling.live_seconds = 1
    p = Poller(cfg, r, clock=Clock(), now_fn=lambda: NOW)
    assert p.floor == 2
    p.poll_now()
    assert p.seconds_until_due("nfl") == 2


# ---------------------------------------------------------------- the thread


def wait_for(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_thread_start_stop_is_immediate():
    p = Poller(make_cfg(["nfl", "nhl"]), ReplaySource(FIXTURES), now_fn=lambda: NOW)
    p.start()
    p.start()  # idempotent
    assert wait_for(lambda: p.snapshot().version >= 2)
    t0 = time.monotonic()
    p.stop()
    assert time.monotonic() - t0 < 1.0
    assert p._thread is not None and not p._thread.is_alive()


def test_thread_survives_failing_source():
    class Boom:
        min_interval = 2.0

        def fetch(self, league):
            raise Exception("always broken")  # noqa: TRY002

    p = Poller(make_cfg(["nfl", "nba"]), Boom(), now_fn=lambda: NOW)
    p.start()
    assert wait_for(lambda: set(p.snapshot().errors) == {"nfl", "nba"})
    assert p._thread.is_alive()
    p.stop()
    assert not p._thread.is_alive()


def test_thread_polls_only_due_leagues():
    clock = Clock()
    src = ScriptedSource({"nfl": [LIVE_BOARD], "nba": [IDLE_BOARD]})
    p = Poller(make_cfg(["nfl", "nba"]), src, clock=clock, now_fn=lambda: NOW)
    p.start()
    assert wait_for(lambda: len(src.calls) >= 2)
    p.stop()
    assert src.calls == ["nfl", "nba"]  # each exactly once; neither due again yet


# ------------------------------------------------------------- sources


def test_replay_source_missing_file_and_reads_file(tmp_path):
    src = ReplaySource(tmp_path)
    assert src.fetch(LEAGUES["nfl"]) == {"events": []}
    (tmp_path / "football_nfl.json").write_text(json.dumps({"events": [1]}))
    assert src.fetch(LEAGUES["nfl"]) == {"events": [1]}
    assert ReplaySource(FIXTURES).fetch(LEAGUES["epl"])["events"]


def test_live_source_defaults():
    live = LiveSource(timeout=3)
    assert live.min_interval == 30 and live.timeout == 3
    live.close()


def fake_games(src, key, n=1):
    for _ in range(n - 1):
        src.fetch(LEAGUES[key])
    return espn.parse_scoreboard(src.fetch(LEAGUES[key]), key)


def test_fake_live_makes_half_the_games_live():
    src = FakeLiveSource(ReplaySource(FIXTURES), seed=3)
    assert src.min_interval == 3
    nba = fake_games(src, "nba")
    assert len(nba) == 4 and sum(g.state == "in" for g in nba) == 2
    epl = fake_games(FakeLiveSource(ReplaySource(FIXTURES), seed=3), "epl")
    assert sum(g.state == "in" for g in epl) == 2
    nfl = fake_games(FakeLiveSource(ReplaySource(FIXTURES), seed=3), "nfl")
    assert sum(g.state == "in" for g in nfl) >= 8


@pytest.mark.parametrize(
    ("key", "pattern"),
    [
        ("nfl", r"^\d{1,2}:\d\d - (1st|2nd|3rd|4th)$"),
        ("nba", r"^\d{1,2}:\d\d - (1st|2nd|3rd|4th)$"),
        ("nhl", r"^\d{1,2}:\d\d - (1st|2nd|3rd)$"),
        ("epl", r"^\d{1,3}'$"),
        ("ncaab", r"^\d{1,2}:\d\d - (1st|2nd)$"),
    ],
)
def test_fake_live_detail_formats(key, pattern):
    src = FakeLiveSource(ReplaySource(FIXTURES), seed=11)
    for _ in range(5):
        games = espn.parse_scoreboard(src.fetch(LEAGUES[key]), key)
        live = [g for g in games if g.state == "in"]
        assert live
        for g in live:
            assert re.match(pattern, g.short_detail), g.short_detail
            assert g.period >= 1
            assert g.home.score is not None and g.away.score is not None


def test_fake_live_football_has_situation_with_valid_possession():
    src = FakeLiveSource(ReplaySource(FIXTURES), seed=5)
    games = espn.parse_scoreboard(src.fetch(LEAGUES["nfl"]), "nfl")
    live = [g for g in games if g.state == "in"]
    assert live and all(g.situation is not None for g in live)
    simulated = [g for g in live if g.situation.possession_team_id]  # some real ones lack it
    assert len(simulated) >= 4
    for g in simulated:
        assert g.competitor_for(g.situation.possession_team_id) is not None
        assert g.situation.short_down_distance


def scores(games):
    return {g.id: (g.away.score, g.home.score) for g in games}


def test_fake_live_changes_scores_and_clocks_over_a_few_fetches():
    for key, step in (("nfl", 3), ("nba", 1), ("nhl", 1), ("epl", 1)):
        src = FakeLiveSource(ReplaySource(FIXTURES), seed=42)
        seen = [espn.parse_scoreboard(src.fetch(LEAGUES[key]), key) for _ in range(12)]
        first, last = scores(seen[0]), scores(seen[-1])
        assert first != last, key
        for a, b in zip(seen, seen[1:], strict=False):
            sa, sb = scores(a), scores(b)
            for gid in sa:
                for old, new in zip(sa[gid], sb[gid], strict=True):
                    if old is not None and new is not None:
                        assert new >= old
                        if key == "nfl" and new != old:
                            assert new - old in (3, 7)
                        if key in ("nhl", "epl") and new != old:
                            assert new - old == 1
        details_first = {g.id: g.short_detail for g in seen[0]}
        details_last = {g.id: g.short_detail for g in seen[-1]}
        assert details_first != details_last, step


def test_fake_live_basketball_increments_are_1_to_3():
    src = FakeLiveSource(ReplaySource(FIXTURES), seed=8)
    prev = scores(espn.parse_scoreboard(src.fetch(LEAGUES["nba"]), "nba"))
    deltas = set()
    for _ in range(60):
        cur = scores(espn.parse_scoreboard(src.fetch(LEAGUES["nba"]), "nba"))
        if any(n < o for gid, pair in cur.items() for o, n in zip(prev[gid], pair, strict=True)):
            break  # the simulation restarted after every game finished
        for gid, pair in cur.items():
            for old, new in zip(prev[gid], pair, strict=True):
                if old is not None and new is not None and new != old:
                    deltas.add(new - old)
        prev = cur
    assert deltas and deltas <= {1, 2, 3}


def test_fake_live_does_not_mutate_inner_and_returns_copies():
    inner_data = json.loads((FIXTURES / "hockey_nhl.json").read_text())
    pristine = copy.deepcopy(inner_data)

    class Inner:
        min_interval = 2.0

        def fetch(self, league):
            return inner_data

    src = FakeLiveSource(Inner(), seed=1)
    out = src.fetch(LEAGUES["nhl"])
    out["events"].clear()  # caller mangling the result must not matter
    assert len(src.fetch(LEAGUES["nhl"])["events"]) == 3
    assert inner_data == pristine


def test_fake_live_is_deterministic_for_a_seed():
    def run():
        src = FakeLiveSource(ReplaySource(FIXTURES), seed=77)
        return [
            [
                (g.id, g.state, g.away.score, g.home.score, g.short_detail)
                for g in espn.parse_scoreboard(src.fetch(LEAGUES["nba"]), "nba")
            ]
            for _ in range(8)
        ]

    assert run() == run()


def test_fake_live_games_finish_and_the_simulation_restarts():
    src = FakeLiveSource(ReplaySource(FIXTURES), seed=2)
    states = []
    for _ in range(300):
        games = espn.parse_scoreboard(src.fetch(LEAGUES["nba"]), "nba")
        states.append(sum(g.state == "in" for g in games))
    assert states[0] == 2 and 0 not in states[:5]
    # some games ended along the way, yet live action is still available at the end
    assert min(states) < 2 or states[-1] > 0
    assert states[-1] > 0


def test_fake_live_tolerates_odd_inner_data():
    class Odd:
        min_interval = 1.0

        def __init__(self, data):
            self.data = data

        def fetch(self, league):
            return self.data

    for data in ({}, {"events": []}, {"events": [None, {}, {"id": 1}]}, {"events": "x"}, []):
        src = FakeLiveSource(Odd(data), seed=1)
        for _ in range(3):
            src.fetch(LEAGUES["nfl"])


def test_poller_end_to_end_with_fake_live():
    cfg = make_cfg(["nfl", "nba"])
    now = datetime.now(UTC)
    p = Poller(
        cfg, FakeLiveSource(ReplaySource(FIXTURES), seed=4), clock=Clock(), now_fn=lambda: now
    )
    first = p.poll_now()
    assert any(g.state == "in" for g in first.games["nba"])
    assert p.seconds_until_due("nba") == 30  # live games -> live cadence
    versions = {first.version}
    for _ in range(10):
        versions.add(p.poll_now().version)
    assert len(versions) > 1  # the render loop would see scores change
