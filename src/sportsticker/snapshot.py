"""Headless snapshot mode: render every slide to PNGs so layouts can be checked
without a panel or a screen.

For each slide it writes:
  raw/<id>.png   the exact 64x32 frame
  led/<id>.png   10x, round LEDs on black (what the panel looks like)
  grid/<id>.png  square pixels with grid lines and x/y rulers
plus animated GIFs (rotation, score flash, transitions), contact sheets for a
quick look, a manifest.json, and optionally an index.html gallery (--site).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from .app import LAYOUT_LOGO_SIZE, Renderer, transition_frames
from .config import TRANSITION_STYLES, Config
from .layouts import LAYOUTS, Highlight
from .models import Game
from .poller import Poller
from .preview import grid_view, led_view, side_by_side
from .slides import Slide, build_playlist
from .sources import FakeLiveSource, LiveSource, ReplaySource
from .status import game_status

log = logging.getLogger(__name__)

DEFAULT_FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "2026-10-11-sun"
GIF_SCALE = 5
MAX_ROTATION_SLIDES = 14
LAYOUT_NAMES = {
    "a": "A · rows",
    "b": "B · big logos",
    "c": "C · logos + big scores",
    "text": "Text",
}


def fixture_time(fixture_dir: Path) -> datetime | None:
    """When a fixture set was recorded (meta.json), so 'today' matches the data."""
    try:
        meta = json.loads((fixture_dir / "meta.json").read_text())
        return datetime.fromisoformat(meta["captured_at"].replace("Z", "+00:00"))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _title(game: Game) -> str:
    return f"{game.away.team.abbr} @ {game.home.team.abbr}"


def _save_gif(frames: list[Image.Image], durations: list[int], path: Path) -> None:
    if not frames:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        disposal=1,
        optimize=False,
    )


class SnapshotWriter:
    def __init__(self, out: Path, scale: int = 10):
        self.out = out
        self.scale = scale
        for sub in ("raw", "led", "grid", "anim"):
            (out / sub).mkdir(parents=True, exist_ok=True)

    def frame(self, frame: Image.Image, ident: str) -> dict:
        frame.save(self.out / "raw" / f"{ident}.png")
        led_view(frame, self.scale).save(self.out / "led" / f"{ident}.png", optimize=True)
        grid_view(frame).save(self.out / "grid" / f"{ident}.png", optimize=True)
        return {
            "id": ident,
            "raw": f"raw/{ident}.png",
            "led": f"led/{ident}.png",
            "grid": f"grid/{ident}.png",
            "pixels": frame.convert("RGB").tobytes().hex(),
        }


def make_source(kind: str, replay_dir: Path | None, timeout: float = 10.0):
    if kind == "live":
        return LiveSource(timeout)
    fixtures = replay_dir or DEFAULT_FIXTURES
    if kind == "replay":
        return ReplaySource(fixtures)
    if kind == "fake-live":
        return FakeLiveSource(ReplaySource(fixtures), seed=7)
    raise ValueError(f"unknown source {kind!r}")


def collect_games(cfg: Config, kind: str, replay_dir: Path | None) -> tuple[dict, datetime]:
    """Fetch once (or a few times for fake-live, so scores change) and return
    (games_by_league, the moment those games represent)."""
    if kind == "live":
        now = datetime.now(UTC)
    else:
        now = fixture_time(replay_dir or DEFAULT_FIXTURES) or datetime.now(UTC)
    source = make_source(kind, replay_dir, cfg.polling.timeout_seconds)
    poller = Poller(cfg, source, now_fn=lambda: now)
    state = poller.poll_now()
    if kind == "fake-live":
        for _ in range(6):  # let the simulation advance clocks and add scores
            state = poller.poll_now()
    if state.errors:
        for league, err in state.errors.items():
            log.warning("%s: %s", league, err)
    return state.games, now


def prepare_logos(cfg: Config, games_by_league: dict):
    from .logos import LogoStore

    sizes = sorted({s for s in LAYOUT_LOGO_SIZE.values() if s})
    store = LogoStore(cfg.logos.cache_dir, sizes, cfg.logos.max_age_days, cfg.display.logo_variant)
    for league, games in games_by_league.items():
        for g in games:
            for t in (g.away.team, g.home.team):
                store.prepare_sync(league, t)
    return store


def _pick_samples(slides: list[Slide]) -> list[Slide]:
    """A handful of games covering different states and edge cases."""
    picks: list[Slide] = []

    def add(pred):
        for s in slides:
            if s.game and pred(s.game) and s not in picks:
                picks.append(s)
                return

    add(lambda g: g.state == "in" and g.situation is not None)
    add(lambda g: g.state == "in")
    add(lambda g: g.state == "pre")
    add(lambda g: g.state == "post")
    add(lambda g: max(len(g.away.team.abbr), len(g.home.team.abbr)) >= 4)
    add(lambda g: max(g.away.score or 0, g.home.score or 0) >= 100)
    add(lambda g: g.away.rank is not None or g.home.rank is not None)
    return picks


def _sheet(images: list[Image.Image], cols: int, gap: int = 12) -> Image.Image:
    rows = [images[i : i + cols] for i in range(0, len(images), cols)]
    w = max(sum(i.width for i in r) + gap * (len(r) - 1) for r in rows)
    h = sum(max(i.height for i in r) for r in rows) + gap * (len(rows) - 1)
    out = Image.new("RGB", (w, h), (12, 12, 12))
    y = 0
    for r in rows:
        x = 0
        for img in r:
            out.paste(img, (x, y))
            x += img.width + gap
        y += max(i.height for i in r) + gap
    return out


def run_snapshot(
    cfg: Config,
    out: Path,
    source: str = "replay",
    replay_dir: Path | None = None,
    layouts: list[str] | None = None,
    site: bool = False,
    scale: int = 10,
) -> dict:
    layouts = layouts or list(LAYOUTS)
    main_layout = cfg.display.layout if cfg.display.layout in layouts else layouts[0]
    out.mkdir(parents=True, exist_ok=True)
    w = SnapshotWriter(out, scale)
    games_by_league, now = collect_games(cfg, source, replay_dir)
    logos = prepare_logos(cfg, games_by_league) if cfg.display.logos else None
    playlist = build_playlist(games_by_league, cfg)
    local = now.astimezone(cfg.tz)

    manifest: dict = {
        "title": "Sportsticker preview",
        "generated_at": datetime.now(UTC).astimezone(cfg.tz).isoformat(timespec="seconds"),
        "data_time": local.isoformat(timespec="minutes"),
        "source": source,
        "timezone": cfg.timezone,
        "logos": bool(logos),
        "width": 64,
        "height": 32,
        "sections": [],
        "comparisons": [],
    }
    if source != "live":
        manifest["note"] = (
            f"Recorded ESPN data from {local:%a %b %-d, %-I:%M %p} {local.tzname()}"
            + (" with simulated live scoring." if source == "fake-live" else ".")
        )

    # 1. The rotation as it would play, in the configured layout.
    renderers = {lay: Renderer(replace_layout(cfg, lay), logos) for lay in layouts}
    rend = renderers[main_layout]
    items = []
    frames_main: list[tuple[Slide, Image.Image]] = []
    for i, slide in enumerate(playlist, 1):
        frame = rend.frame(slide, now)
        frames_main.append((slide, frame))
        if slide.game:
            g = slide.game
            ident = f"{main_layout}-{i:02d}-{g.league}-{_slug(_title(g))}"
            st = game_status(g, cfg.tz, now)
            sub = f"{st.line} · {g.league.upper()}" + (" · ★" if slide.favorite else "")
            item = w.frame(frame, ident) | {"title": _title(g), "subtitle": sub}
        else:
            item = w.frame(frame, f"{main_layout}-{i:02d}-clock") | {
                "title": "No games",
                "subtitle": "clock screen",
            }
        item |= {"layout": main_layout, "duration": slide.duration}
        items.append(item)
    manifest["sections"].append(
        {
            "title": f"Rotation ({len(items)} slides, layout {LAYOUT_NAMES[main_layout]})",
            "description": "Live first, then upcoming by start time, then finals. "
            "Favorites first within each group.",
            "items": items,
        }
    )

    # 2. Layout comparison on a few representative games.
    samples = _pick_samples(playlist)
    comp_items = []
    for s in samples:
        imgs = {}
        for lay in layouts:
            frame = renderers[lay].frame(s, now)
            ident = f"cmp-{lay}-{s.game.league}-{_slug(_title(s.game))}"
            item = w.frame(frame, ident)
            imgs[lay] = item["led"]
            st = game_status(s.game, cfg.tz, now)
            comp_items.append(
                item
                | {
                    "title": f"{_title(s.game)} · {LAYOUT_NAMES[lay]}",
                    "subtitle": f"{st.line} · {s.game.league.upper()}",
                    "layout": lay,
                }
            )
        manifest["comparisons"].append({"title": _title(s.game), "images": imgs})
    if comp_items:
        manifest["sections"].append(
            {
                "title": "Layouts side by side",
                "description": "Set display.layout in config.yaml to a, b, c or text.",
                "items": comp_items,
            }
        )

    # 3. Special screens and animations.
    specials = []
    clock_frame = Renderer(cfg).frame(Slide("clock"), now)
    specials.append(
        w.frame(clock_frame, "clock") | {"title": "No games today", "subtitle": "clock and date"}
    )
    live = next((s for s in playlist if s.game and s.game.state == "in"), None)
    flash_src = live or next((s for s in playlist if s.game), None)
    if flash_src:
        g = flash_src.game
        if live is None:  # no live game in the data: fake one so the flash can be seen
            g = replace(g, state="in", short_detail="8:01 - 3rd", display_clock="8:01", period=3)
            g = replace(g, home=replace(g.home, score=(g.home.score or 0) + 7))
            g = replace(g, away=replace(g.away, score=g.away.score or 0))
            flash_src = Slide("game", g)
        frames, durs = [], []
        for k in range(12):
            hl = Highlight("home", k % 2 == 0)
            frames.append(led_view(rend.frame(flash_src, now, hl), GIF_SCALE))
            durs.append(250)
        frames.append(led_view(rend.frame(flash_src, now), GIF_SCALE))
        durs.append(1500)
        _save_gif(frames, durs, out / "anim" / "score-flash.gif")
        still = rend.frame(flash_src, now, Highlight("home", True))
        specials.append(
            w.frame(still, "score-flash")
            | {
                "title": f"Score! {g.home.team.abbr}",
                "subtitle": "scoring team flashes for a few seconds",
                "gif": "anim/score-flash.gif",
            }
        )
    game_frames = [f for s, f in frames_main if s.game]
    if len(game_frames) >= 2:
        for style in TRANSITION_STYLES:
            a, b = game_frames[0], game_frames[1]
            steps = max(2, round(cfg.display.transition_ms / 1000 * cfg.display.animation_fps))
            seq = [a] + transition_frames(style, a, b, steps) + [b]
            durs = [1200] + [round(1000 / cfg.display.animation_fps)] * steps + [1200]
            _save_gif([led_view(f, GIF_SCALE) for f in seq], durs, out / "anim" / f"{style}.gif")
            mid = seq[len(seq) // 2]
            specials.append(
                w.frame(mid, f"transition-{style}")
                | {
                    "title": f"Transition: {style}",
                    "subtitle": "display.transition_style"
                    + (" (current)" if style == cfg.display.transition_style else ""),
                    "gif": f"anim/{style}.gif",
                }
            )
    manifest["sections"].append({"title": "Special screens and animations", "items": specials})

    # 4. Rotation GIF: slides held for their real duration, with transitions.
    rot = [f for _, f in frames_main][:MAX_ROTATION_SLIDES]
    seq, durs = [], []
    fps = cfg.display.animation_fps
    steps = max(2, round(cfg.display.transition_ms / 1000 * min(fps, 15)))
    for i, f in enumerate(rot):
        seq.append(led_view(f, GIF_SCALE))
        durs.append(round(frames_main[i][0].duration * 1000))
        if cfg.display.transitions and len(rot) > 1:
            nxt = rot[(i + 1) % len(rot)]
            for t in transition_frames(cfg.display.transition_style, f, nxt, steps):
                seq.append(led_view(t, GIF_SCALE))
                durs.append(round(cfg.display.transition_ms / steps))
    _save_gif(seq, durs, out / "rotation.gif")
    manifest["rotation"] = {
        "gif": "rotation.gif",
        "slides": len(rot),
        "seconds": round(sum(durs) / 1000),
    }

    # 5. Contact sheets for a quick look.
    overview = [led_view(f, scale) for _, f in frames_main[:12]]
    _sheet(overview, 3).save(out / "overview.png", optimize=True)
    if samples:
        rows = []
        for s in samples[:4]:
            rows.append(
                side_by_side([led_view(renderers[lay].frame(s, now), 6) for lay in layouts])
            )
        _sheet(rows, 1).save(out / "layouts.png", optimize=True)

    (out / "manifest.json").write_text(json.dumps(_strip_pixels(manifest), indent=1))
    if site:
        from .site import write_index

        write_index(out, manifest)
    log.info("snapshot: %d slides -> %s", len(playlist), out)
    return manifest


def _strip_pixels(manifest: dict) -> dict:
    """manifest.json without the bulky pixel hex (it is embedded in index.html)."""
    m = json.loads(json.dumps(manifest))
    for sec in m.get("sections", []):
        for it in sec.get("items", []):
            it.pop("pixels", None)
    return m


def replace_layout(cfg: Config, layout: str) -> Config:
    return replace(cfg, display=replace(cfg.display, layout=layout))


__all__ = ["run_snapshot", "fixture_time", "DEFAULT_FIXTURES"]
