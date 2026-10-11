import threading
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from sportsticker.app import Renderer, TickerApp, transition_frames
from sportsticker.backend import HeadlessBackend
from sportsticker.config import TRANSITION_STYLES, load_config
from sportsticker.espn import parse_scoreboard
from sportsticker.layouts import LAYOUTS, Highlight, RenderContext, render_clock
from sportsticker.models import LEAGUES, Competitor, Game, Situation, Team
from sportsticker.poller import ScoreState
from sportsticker.slides import ScoreTracker, Slide, build_playlist, order_games
from sportsticker.status import game_status

FIXTURES = Path(__file__).parent / "fixtures" / "2026-10-11-sun"
TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 11, 18, 56, tzinfo=UTC)


def all_fixture_games() -> list[Game]:
    import json

    games = []
    for key in ("nfl", "ncaaf", "nba", "ncaab", "nhl", "epl"):
        lg = LEAGUES[key]
        f = FIXTURES / f"{lg.sport}_{lg.league}.json"
        games += parse_scoreboard(json.loads(f.read_text()), key)
    return games


def mk(league="nfl", state="in", a="BUF", h="KC", sa=10, sh=14, detail="", clock="", period=0,
       sit=None):  # fmt: skip
    return Game(
        id=f"{a}{h}",
        league=league,
        state=state,
        start=datetime(2026, 10, 11, 23, 20, tzinfo=UTC),
        away=Competitor(Team(a, color="00338d", id="1"), False, sa),
        home=Competitor(Team(h, color="e31837", id="2"), True, sh),
        short_detail=detail,
        display_clock=clock,
        period=period,
        situation=sit,
    )


@pytest.fixture
def cfg():
    return load_config(Path(__file__).parents[1] / "config.yaml")


@pytest.mark.parametrize(
    "game,expected",
    [
        (mk(detail="4:12 - 3rd", clock="4:12", period=3), "Q3 4:12"),
        (mk(league="ncaab", detail="2:31 - 2nd Half", clock="2:31", period=2), "2H 2:31"),
        (mk(league="nhl", detail="12:30 - 2nd", clock="12:30", period=2), "P2 12:30"),
        (mk(league="nba", detail="3:00 - OT", clock="3:00", period=5), "OT 3:00"),
        (mk(league="epl", detail="62'", clock="62'", period=2), "62'"),
        (mk(detail="Halftime", period=2), "HALF"),
        (mk(detail="End of 1st", period=1), "END Q1"),
        (mk(state="post", detail="Final"), "FINAL"),
        (mk(state="post", detail="Final/OT"), "FINAL/OT"),
        (mk(state="post", detail="Postponed"), "PPD"),
        (mk(state="pre", detail="Sun, October 11th at 7:20 PM EDT"), "7:20 PM"),
    ],
)
def test_status_text(game, expected):
    assert game_status(game, TZ, NOW).line == expected


def test_down_and_distance_is_compact():
    g = mk(detail="4:12 - 3rd", clock="4:12", period=3, sit=Situation("2", "3rd & 10", "3rd & 10"))
    assert game_status(g, TZ, NOW).detail == "3&10"


@pytest.mark.parametrize("layout", list(LAYOUTS))
def test_every_layout_renders_every_fixture_game(layout):
    games = all_fixture_games()
    assert len(games) > 20
    ctx = RenderContext(TZ, NOW)
    for g in games:
        for hl in (Highlight(), Highlight("home", False), Highlight("away", True)):
            img = LAYOUTS[layout](g, ctx, hl)
            assert img.size == (64, 32)
            assert img.mode == "RGB"
            assert img.getbbox() is not None


def test_pre_game_hides_zero_scores():
    pre = mk(state="pre", sa=0, sh=0)
    live = replace(pre, state="in", short_detail="1:00 - 1st", period=1)
    ctx = RenderContext(TZ, NOW)
    # The score column (right edge) is empty before the game, not "0".
    assert LAYOUTS["a"](pre, ctx, Highlight()).crop((50, 0, 64, 25)).getbbox() is None
    assert LAYOUTS["a"](live, ctx, Highlight()).crop((50, 0, 64, 25)).getbbox() is not None


def test_flash_blinks_and_changes_score_color():
    ctx = RenderContext(TZ, NOW)
    g = mk(detail="4:12 - 3rd", clock="4:12", period=3)
    plain = LAYOUTS["a"](g, ctx, Highlight())
    on = LAYOUTS["a"](g, ctx, Highlight("home", True))
    assert plain.tobytes() != on.tobytes()


def test_clock_screen():
    img = render_clock(datetime(2026, 10, 11, 19, 42))
    assert img.size == (64, 32) and img.getbbox() is not None


def test_order_live_upcoming_final_favorites_first(cfg):
    games = {
        "nfl": [
            mk(state="post", a="DAL", h="NYG"),
            mk(state="in", a="BUF", h="MIA"),
            mk(state="in", a="LV", h="KC"),  # favorite
            mk(state="pre", a="SF", h="SEA"),
        ],
        "nba": [mk(league="nba", state="pre", a="CHA", h="BOS")],  # favorite, later start
    }
    games["nba"][0] = replace(games["nba"][0], start=datetime(2026, 10, 12, 0, 0, tzinfo=UTC))
    order = [f"{g.away.team.abbr}{g.home.team.abbr}" for g in order_games(games, cfg)]
    assert order == ["LVKC", "BUFMIA", "CHABOS", "SFSEA", "DALNYG"]


def test_playlist_dwell_and_clock_fallback(cfg):
    pl = build_playlist({"nfl": [mk(a="LV", h="KC")]}, cfg)
    assert pl[0].duration == cfg.display.favorite_live_seconds
    assert build_playlist({}, cfg)[0].kind == "clock"


def test_score_tracker():
    t = ScoreTracker()
    assert t.update([mk(sa=0, sh=0)]) == []  # first sight never flashes
    ev = t.update([mk(sa=0, sh=7)])
    assert [(e.side, e.points) for e in ev] == [("home", 7)]
    assert t.update([mk(sa=0, sh=7)]) == []


@pytest.mark.parametrize("style", TRANSITION_STYLES)
def test_transitions_end_on_new_frame(style, cfg):
    r = Renderer(cfg)
    a = r.frame(Slide("game", mk(a="BUF", h="KC")), NOW)
    b = r.frame(Slide("game", mk(a="DAL", h="NYG")), NOW)
    frames = transition_frames(style, a, b, 8)
    assert len(frames) == 8
    assert frames[-1].tobytes() == b.tobytes()


def test_renderer_caches_frames(cfg):
    r = Renderer(cfg)
    s = Slide("game", mk())
    r.frame(s, NOW)
    r.frame(s, NOW)
    assert r.renders == 1


class FakePoller:
    def __init__(self, games):
        self.state = ScoreState(games=games, updated_at={}, errors={}, version=1)

    def set(self, games):
        self.state = ScoreState(games, {}, {}, self.state.version + 1)

    def snapshot(self):
        return self.state


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_app_rotates_flashes_and_only_redraws_on_change(cfg):
    cfg = replace(cfg, display=replace(cfg.display, transitions=False, slide_seconds=6))
    a = mk(a="BUF", h="MIA", sa=0, sh=0)
    b = mk(a="DAL", h="NYG", sa=3, sh=0)
    poller = FakePoller({"nfl": [a, b]})
    clock = FakeClock()
    backend = HeadlessBackend()
    app = TickerApp(cfg, backend, poller, clock=clock, now_fn=lambda: NOW)
    stop = threading.Event()

    def run_for(seconds):
        end = clock.t + seconds
        while clock.t < end:
            clock.t += app.step(stop)

    run_for(5)
    assert app.current.game.home.team.abbr == "MIA"
    shown_static = backend.frames_shown
    run_for(0.9)
    assert backend.frames_shown == shown_static  # nothing changed -> no redraw
    run_for(2)
    assert app.current.game.home.team.abbr == "NYG"  # rotated after 6 s

    # MIA scores while NYG is on screen: it becomes the next slide and flashes.
    poller.set({"nfl": [replace(a, home=replace(a.home, score=7)), b]})
    run_for(0.6)
    run_for(6)
    assert app.current.game.home.team.abbr == "MIA"
    before = backend.frames_shown
    run_for(1.0)
    assert backend.frames_shown - before >= 3  # blinking at 4 Hz


def test_app_night_brightness(cfg):
    backend = HeadlessBackend()
    night = datetime(2026, 10, 12, 4, 0, tzinfo=UTC)  # midnight in New York
    app = TickerApp(cfg, backend, FakePoller({}), clock=FakeClock(), now_fn=lambda: night)
    app.step()
    assert backend.brightness == cfg.brightness.night


def test_snapshot_replay(tmp_path, cfg):
    from sportsticker.snapshot import run_snapshot

    cfg = replace(cfg, display=replace(cfg.display, logos=False))
    m = run_snapshot(cfg, tmp_path, "replay", layouts=["a", "b"])
    assert (tmp_path / "rotation.gif").exists()
    assert (tmp_path / "overview.png").exists()
    first = m["sections"][0]["items"][0]
    assert (tmp_path / first["raw"]).exists()
    assert len(first["pixels"]) == 64 * 32 * 6
