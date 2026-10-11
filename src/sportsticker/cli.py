"""Command line: run | snapshot | logos | fixtures. CLI flags override config.yaml."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from .config import LAYOUTS, TRANSITION_STYLES, Config, ConfigError, load_config
from .models import LEAGUES

log = logging.getLogger("sportsticker")


def _leagues(value: str) -> list[str]:
    keys = [k.strip().lower() for k in value.split(",") if k.strip()]
    bad = [k for k in keys if k not in LEAGUES]
    if bad:
        raise argparse.ArgumentTypeError(
            f"unknown league(s) {', '.join(bad)} (known: {', '.join(LEAGUES)})"
        )
    return keys


def _layouts(value: str) -> list[str]:
    keys = [k.strip().lower() for k in value.split(",") if k.strip()]
    bad = [k for k in keys if k not in LAYOUTS]
    if bad:
        raise argparse.ArgumentTypeError(f"unknown layout(s) {', '.join(bad)}")
    return keys


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default="config.yaml", help="path to config.yaml")
    common.add_argument("--leagues", type=_leagues, help="comma list overriding config leagues")
    common.add_argument("--layout", choices=LAYOUTS)
    common.add_argument("--no-logos", action="store_true", help="abbreviations only")
    common.add_argument("--logo-cache", type=Path, help="logo cache directory")
    common.add_argument(
        "--log-level", default="info", choices=("debug", "info", "warning", "error")
    )

    p = argparse.ArgumentParser(prog="sportsticker", description=__doc__, parents=[common])
    sub = p.add_subparsers(dest="command")

    run = sub.add_parser("run", parents=[common], help="drive the display (default)")
    _run_args(run)
    _run_args(p)  # so `python -m sportsticker --replay` works without "run"

    snap = sub.add_parser("snapshot", parents=[common], help="render every slide to PNG")
    snap.add_argument("--out", type=Path, default=Path("snapshots"))
    snap.add_argument("--source", choices=("replay", "live", "fake-live"), default="replay")
    snap.add_argument("--replay", type=Path, metavar="DIR", help="fixture dir for replay")
    snap.add_argument("--layouts", type=_layouts, help="layouts to render (default all)")
    snap.add_argument("--site", action="store_true", help="also write index.html gallery")
    snap.add_argument("--scale", type=int, default=10, help="LED preview scale (px per LED)")

    lg = sub.add_parser("logos", parents=[common], help="pre-fetch logos for enabled leagues")
    lg.add_argument("--workers", type=int, default=4)

    fx = sub.add_parser("fixtures", parents=[common], help="save ESPN responses as fixtures")
    fx.add_argument("--out", type=Path, required=True)
    return p


def _run_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--backend", choices=("auto", "hardware", "emulator", "headless"), default="auto"
    )
    p.add_argument("--brightness", type=int, help="day brightness 0-100")
    p.add_argument("--slide-seconds", type=float)
    p.add_argument(
        "--replay",
        nargs="?",
        const="__default__",
        metavar="DIR",
        help="play recorded fixtures (default: bundled set) instead of live data",
    )
    p.add_argument("--fake-live", action="store_true", help="simulate live games and scoring")
    p.add_argument("--transitions", dest="transitions", action="store_true", default=None)
    p.add_argument("--no-transitions", dest="transitions", action="store_false")
    p.add_argument("--transition-style", choices=TRANSITION_STYLES)
    p.add_argument("--profile", action="store_true", help="log frame times, CPU and memory")
    p.add_argument("--check-config", action="store_true", help="validate config and exit")
    p.add_argument("--duration", type=float, help="exit after this many seconds")


def apply_overrides(cfg: Config, a: argparse.Namespace) -> Config:
    d, b, lg = cfg.display, cfg.brightness, cfg.logos
    if getattr(a, "leagues", None):
        cfg = replace(cfg, leagues=a.leagues)
    if getattr(a, "layout", None):
        d = replace(d, layout=a.layout)
    if getattr(a, "no_logos", False):
        d = replace(d, logos=False)
    if getattr(a, "slide_seconds", None):
        d = replace(d, slide_seconds=a.slide_seconds)
    if getattr(a, "transitions", None) is not None:
        d = replace(d, transitions=a.transitions)
    if getattr(a, "transition_style", None):
        d = replace(d, transition_style=a.transition_style)
    if getattr(a, "brightness", None) is not None:
        if not 0 <= a.brightness <= 100:
            raise ConfigError(["--brightness must be 0-100"])
        b = replace(b, day=a.brightness)
    if getattr(a, "logo_cache", None):
        lg = replace(lg, cache_dir=a.logo_cache.expanduser())
    return replace(cfg, display=d, brightness=b, logos=lg)


def _cmd_run(cfg: Config, a: argparse.Namespace) -> int:
    from .app import TickerApp
    from .backend import create_backend
    from .poller import Poller
    from .profile import Profiler
    from .snapshot import DEFAULT_FIXTURES, fixture_time
    from .sources import FakeLiveSource, LiveSource, ReplaySource

    poll_now_fn = lambda: datetime.now(UTC)  # noqa: E731
    if a.replay:
        fixtures = DEFAULT_FIXTURES if a.replay == "__default__" else Path(a.replay)
        source = ReplaySource(fixtures)
        captured = fixture_time(fixtures)
        if captured:  # make "today" match the recorded data, with time moving on
            offset = captured - datetime.now(UTC)
            poll_now_fn = lambda: datetime.now(UTC) + offset  # noqa: E731
    else:
        source = LiveSource(cfg.polling.timeout_seconds)
    if a.fake_live:
        source = FakeLiveSource(source)

    logos = None
    if cfg.display.logos:
        from .app import LAYOUT_LOGO_SIZE
        from .logos import LogoStore

        sizes = sorted({s for s in LAYOUT_LOGO_SIZE.values() if s})
        logos = LogoStore(
            cfg.logos.cache_dir, sizes, cfg.logos.max_age_days, cfg.display.logo_variant
        )

    backend = create_backend(a.backend, cfg.matrix, cfg.brightness.day)
    poller = Poller(cfg, source, now_fn=poll_now_fn)
    app = TickerApp(
        cfg,
        backend,
        poller,
        logos=logos,
        profiler=Profiler(a.profile),
        now_fn=poll_now_fn if a.replay else (lambda: datetime.now(UTC)),
    )
    stop = threading.Event()

    def _signal(signum, _frame):
        log.info("signal %s: stopping", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _signal)
    signal.signal(signal.SIGINT, _signal)
    if a.duration:
        threading.Timer(a.duration, stop.set).start()

    poller.start()
    try:
        app.run(stop)
    finally:
        poller.stop()
        if logos is not None:
            logos.close()
    if a.profile and app.profiler.history:
        h = app.profiler.history
        log.info(
            "profile summary: render-thread CPU avg %.2f%%, max compose %.2f ms, RSS %.1f MB",
            sum(x["render_cpu_pct"] for x in h) / len(h),
            max(x["compose_max_ms"] for x in h),
            h[-1]["rss_mb"],
        )
    return 0


def _cmd_snapshot(cfg: Config, a: argparse.Namespace) -> int:
    from .snapshot import run_snapshot

    m = run_snapshot(cfg, a.out, a.source, a.replay, a.layouts, a.site, a.scale)
    n = sum(len(s["items"]) for s in m["sections"])
    print(f"wrote {n} frames to {a.out}/ (overview.png, layouts.png, rotation.gif, anim/)")
    if a.site:
        print(f"open {a.out}/index.html")
    return 0


def _cmd_logos(cfg: Config, a: argparse.Namespace) -> int:
    from .app import LAYOUT_LOGO_SIZE
    from .logos import LogoStore, prefetch

    sizes = sorted({s for s in LAYOUT_LOGO_SIZE.values() if s})
    store = LogoStore(cfg.logos.cache_dir, sizes, cfg.logos.max_age_days, cfg.display.logo_variant)
    counts = prefetch(cfg.leagues, store, workers=a.workers)
    for k, v in counts.items():
        print(f"{k:>14}: {v}")
    print(f"cache: {cfg.logos.cache_dir}")
    return 0 if not any(v for k, v in counts.items() if k.endswith("_failed")) else 1


def _cmd_fixtures(cfg: Config, a: argparse.Namespace) -> int:
    import json

    from .espn import save_fixtures

    paths = save_fixtures(cfg.leagues, a.out)
    meta = {"captured_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
    (a.out / "meta.json").write_text(json.dumps(meta) + "\n")
    for p in paths:
        print(p)
    return 0


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, a.log_level.upper()),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        cfg = apply_overrides(load_config(a.config), a)
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    command = a.command or "run"
    if command == "run" and a.check_config:
        print(f"{a.config}: OK ({', '.join(cfg.leagues)}; layout {cfg.display.layout})")
        return 0
    handler = {
        "run": _cmd_run,
        "snapshot": _cmd_snapshot,
        "logos": _cmd_logos,
        "fixtures": _cmd_fixtures,
    }[command]
    return handler(cfg, a)


__all__ = ["main"]
