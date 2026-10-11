"""Frame composition (Renderer) and the main display loop (TickerApp).

The loop is event-driven: it pushes a frame only when the picture changes
(new slide, new data, score-flash blink, clock minute, transition step) and
otherwise sleeps. It never touches the network; it reads the poller's latest
snapshot, which is a cheap lock-protected copy.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from PIL import Image

from .backend import Backend
from .config import Config, in_window
from .layouts import LAYOUTS, NO_HIGHLIGHT, Highlight, RenderContext, preload_fonts, render_clock
from .profile import Profiler
from .slides import ScoreTracker, Slide, build_playlist

log = logging.getLogger(__name__)

# Logo box size each layout requests (see layouts/*).
LAYOUT_LOGO_SIZE = {"a": 12, "b": 21, "c": 15, "text": None}
BLINK_PERIOD = 0.25  # seconds per on/off phase of the score flash
DATA_CHECK = 0.5  # how often the loop looks for new poller data
FLASH_PENDING_MAX_AGE = 120.0  # a score older than this no longer flashes


class Renderer:
    """Builds 64x32 frames, caching every rendered image.

    A slide is rendered once per distinct (game data, highlight phase, logo
    availability); afterwards showing it is a dictionary lookup.
    """

    def __init__(self, cfg: Config, logos=None, cache_size: int = 96):
        self.cfg = cfg
        self.logos = logos if cfg.display.logos else None
        self.layout = cfg.display.layout
        self._cache: OrderedDict = OrderedDict()
        self._cache_size = cache_size
        self.renders = 0  # cache misses, for profiling/tests
        preload_fonts()

    def context(self, now: datetime) -> RenderContext:
        return RenderContext(
            tz=self.cfg.tz,
            now=now,
            logos=self.logos,
            show_situation=self.cfg.display.show_situation,
        )

    def _logo_key(self, slide: Slide, layout: str) -> tuple:
        size = LAYOUT_LOGO_SIZE.get(layout)
        if not size or self.logos is None or slide.game is None:
            return ()
        g = slide.game
        try:
            return tuple(
                id(self.logos.get(g.league, t.abbr, size)) for t in (g.away.team, g.home.team)
            )
        except Exception:  # noqa: BLE001
            return ()

    def frame(
        self,
        slide: Slide,
        now: datetime,
        hl: Highlight = NO_HIGHLIGHT,
        layout: str | None = None,
    ) -> Image.Image:
        layout = layout or self.layout
        local = now.astimezone(self.cfg.tz)
        if slide.kind == "clock":
            key = ("clock", local.strftime("%Y%m%d%H%M"))
        else:
            key = (layout, slide.game, hl, self._logo_key(slide, layout), local.date())
        img = self._cache.get(key)
        if img is not None:
            self._cache.move_to_end(key)
            return img
        self.renders += 1
        if slide.kind == "clock":
            img = render_clock(local)
        else:
            img = LAYOUTS[layout](slide.game, self.context(now), hl)
        self._cache[key] = img
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return img


def _ease(t: float) -> float:
    return 1 - (1 - t) ** 3  # ease-out cubic: fast start, gentle landing


def transition_frames(style: str, old: Image.Image, new: Image.Image, steps: int) -> list:
    """Intermediate frames from `old` to `new` (the final frame equals `new`).

    push:  old slides out left while new enters from the right
    split: top half (away team) enters from the left, bottom half from the right
    wipe:  new is revealed left to right behind a bright leading edge
    fade:  cross-dissolve
    """
    w, h = old.size
    out = []
    for i in range(1, steps + 1):
        t = _ease(i / steps)
        if style == "fade":
            out.append(Image.blend(old, new, t))
            continue
        f = Image.new("RGB", old.size)
        off = round(w * t)
        if style == "split":
            mid = h // 2 - 3  # the two team rows sit above row ~13 in every layout
            f.paste(old.crop((0, 0, w, mid)), (off, 0))
            f.paste(new.crop((0, 0, w, mid)), (off - w, 0))
            f.paste(old.crop((0, mid, w, h)), (-off, mid))
            f.paste(new.crop((0, mid, w, h)), (w - off, mid))
        elif style == "wipe":
            f.paste(old, (0, 0))
            if off:
                f.paste(new.crop((0, 0, off, h)), (0, 0))
            if 0 < off < w:
                f.paste((255, 255, 255), (off, 0, off + 1, h))
                if off > 0:
                    f.paste((90, 90, 90), (off - 1, 0, off, h))
        else:  # push
            f.paste(old, (-off, 0))
            f.paste(new, (w - off, 0))
        out.append(f)
    return out


def push_frames(old: Image.Image, new: Image.Image, steps: int) -> list[Image.Image]:
    return transition_frames("push", old, new, steps)


@dataclass
class _Flash:
    side: str
    detected: float  # monotonic time the score was seen
    until: float = 0.0  # set when the slide is on screen


class TickerApp:
    def __init__(
        self,
        cfg: Config,
        backend: Backend,
        poller,
        logos=None,
        profiler: Profiler | None = None,
        clock: Callable[[], float] = time.monotonic,
        now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.cfg = cfg
        self.backend = backend
        self.poller = poller
        self.logos = logos if cfg.display.logos else None
        self.renderer = Renderer(cfg, self.logos)
        self.profiler = profiler or Profiler(False)
        self.clock = clock
        self.now_fn = now_fn
        self.tracker = ScoreTracker()
        self.playlist: list[Slide] = [Slide("clock", duration=cfg.display.slide_seconds)]
        self.index = 0
        self.slide_started = clock()
        self.flashes: dict[str, _Flash] = {}
        self.version = -1
        self.last_frame: Image.Image | None = None
        self.brightness: int | None = None
        self._requested_logos: set[tuple[str, str]] = set()

    # ---- data ---------------------------------------------------------------

    def _refresh_data(self, now_m: float) -> None:
        snap = self.poller.snapshot()
        if snap.version == self.version:
            return
        self.version = snap.version
        all_games = [g for lst in snap.games.values() for g in lst]
        if self.logos is not None:
            for g in all_games:
                for t in (g.away.team, g.home.team):
                    if (g.league, t.abbr) not in self._requested_logos:
                        self._requested_logos.add((g.league, t.abbr))
                        self.logos.request(g.league, t)
        events = self.tracker.update(all_games)
        current_key = self.current.key
        new_playlist = build_playlist(snap.games, self.cfg)
        for ev in events:
            log.info("score: %s %s +%d", ev.game_key, ev.side, ev.points)
            self.flashes[ev.game_key] = _Flash(ev.side, now_m)
        self._set_playlist(new_playlist, current_key, now_m, [e.game_key for e in events])

    def _set_playlist(
        self, playlist: list[Slide], current_key: str, now_m: float, scored: list[str]
    ) -> None:
        keys = [s.key for s in playlist]
        self.playlist = playlist
        if current_key in keys:
            self.index = keys.index(current_key)
        else:
            self.index = min(self.index, len(playlist) - 1)
            self.slide_started = now_m
        # A game that just scored becomes the next slide (or flashes right away).
        for key in scored:
            if key == self.current.key:
                fl = self.flashes.get(key)
                if fl:
                    fl.until = now_m + self.cfg.display.score_flash_seconds
            elif key in keys:
                slide = self.playlist.pop(keys.index(key))
                if keys.index(key) < self.index:
                    self.index -= 1
                self.playlist.insert(self.index + 1, slide)
                keys = [s.key for s in self.playlist]

    # ---- slides -------------------------------------------------------------

    @property
    def current(self) -> Slide:
        return self.playlist[self.index % len(self.playlist)]

    def _slide_duration(self, slide: Slide) -> float:
        d = slide.duration
        fl = self.flashes.get(slide.key)
        if fl and fl.until:
            d = max(d, fl.until - self.slide_started + 0.5)
        return d

    def _advance(self, now_m: float) -> Slide:
        self.index = (self.index + 1) % len(self.playlist)
        self.slide_started = now_m
        slide = self.current
        fl = self.flashes.get(slide.key)
        if fl:
            if now_m - fl.detected <= FLASH_PENDING_MAX_AGE:
                fl.until = now_m + self.cfg.display.score_flash_seconds
            else:
                del self.flashes[slide.key]
        return slide

    def _highlight(self, slide: Slide, now_m: float) -> Highlight:
        fl = self.flashes.get(slide.key)
        if not fl or not fl.until:
            return NO_HIGHLIGHT
        if now_m >= fl.until:
            del self.flashes[slide.key]
            return NO_HIGHLIGHT
        phase = int((now_m - (fl.until - self.cfg.display.score_flash_seconds)) / BLINK_PERIOD)
        return Highlight(fl.side, phase % 2 == 0)

    # ---- output -------------------------------------------------------------

    def _show(self, frame: Image.Image, compose_s: float = 0.0) -> None:
        if frame is self.last_frame:
            return
        t = time.perf_counter()
        self.backend.show(frame)
        self.profiler.record(compose_s, time.perf_counter() - t)
        self.last_frame = frame

    def _update_brightness(self, now: datetime) -> None:
        b = self.cfg.brightness
        local = now.astimezone(self.cfg.tz).time()
        target = b.night if in_window(local, b.night_start, b.night_end) else b.day
        if target != self.brightness:
            log.info("brightness -> %d", target)
            self.backend.set_brightness(target)
            self.brightness = target

    def _transition(self, old: Image.Image, new: Image.Image, stop: threading.Event) -> None:
        d = self.cfg.display
        steps = max(2, round(d.transition_ms / 1000 * d.animation_fps))
        dt = 1.0 / d.animation_fps
        next_t = self.clock()
        for f in transition_frames(d.transition_style, old, new, steps):
            t0 = time.perf_counter()
            self._show(f, time.perf_counter() - t0)
            next_t += dt
            if stop.wait(max(0.0, next_t - self.clock())):
                return

    def step(self, stop: threading.Event | None = None) -> float:
        """Run one loop iteration; returns seconds until the next one is needed."""
        stop = stop or threading.Event()
        now_m = self.clock()
        now = self.now_fn()
        self._refresh_data(now_m)
        self._update_brightness(now)

        transition_from = None
        if now_m - self.slide_started >= self._slide_duration(self.current):
            if len(self.playlist) > 1:
                transition_from = self.last_frame
            self._advance(now_m)

        slide = self.current
        hl = self._highlight(slide, now_m)
        t0 = time.perf_counter()
        frame = self.renderer.frame(slide, now, hl)
        compose = time.perf_counter() - t0
        if transition_from is not None and self.cfg.display.transitions:
            self._transition(transition_from, frame, stop)
        self._show(frame, compose)
        self.profiler.tick()

        # Sleep until the next thing that can change the picture.
        waits = [self._slide_duration(slide) - (self.clock() - self.slide_started), DATA_CHECK]
        if hl.side:
            waits.append(BLINK_PERIOD - ((now_m - self.slide_started) % BLINK_PERIOD))
        if slide.kind == "clock":
            waits.append(60 - now.second - now.microsecond / 1e6 + 0.01)
        return max(0.01, min(waits))

    def run(self, stop: threading.Event) -> None:
        log.info("display loop started (layout %s)", self.cfg.display.layout)
        while not stop.is_set():
            try:
                wait = self.step(stop)
            except Exception:  # noqa: BLE001 - never let one bad frame kill the display
                log.exception("render step failed")
                wait = 1.0
            stop.wait(wait)
        self.backend.close()
