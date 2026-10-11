"""Load and validate config.yaml into typed dataclasses.

Validation collects every problem and raises one ConfigError listing them all,
so a bad config file is fixed in one pass instead of one error at a time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from .models import LEAGUES

LAYOUTS = ("a", "b", "c", "text")
LOGO_VARIANTS = ("auto", "logo", "dark")
TRANSITION_STYLES = ("push", "split", "wipe", "fade")
MIN_POLL_SECONDS = 30

# RGBMatrixOptions attributes we pass through, with the type each must have.
MATRIX_OPTIONS: dict[str, type] = {
    "rows": int,
    "cols": int,
    "chain_length": int,
    "parallel": int,
    "hardware_mapping": str,
    "gpio_slowdown": int,
    "brightness": int,
    "panel_type": str,
    "pwm_bits": int,
    "pwm_lsb_nanoseconds": int,
    "pwm_dither_bits": int,
    "scan_mode": int,
    "multiplexing": int,
    "row_address_type": int,
    "led_rgb_sequence": str,
    "pixel_mapper_config": str,
    "limit_refresh_rate_hz": int,
    "show_refresh_rate": bool,
    "disable_hardware_pulsing": bool,
    "drop_privileges": bool,
}


class ConfigError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("Invalid config:\n  - " + "\n  - ".join(problems))


@dataclass
class DisplayConfig:
    layout: str = "a"
    logo_variant: str = "auto"
    logos: bool = True
    slide_seconds: float = 6.0
    favorite_live_seconds: float = 10.0
    score_flash_seconds: float = 4.0
    show_situation: bool = True
    transitions: bool = True
    transition_style: str = "push"
    transition_ms: int = 400
    animation_fps: int = 30


@dataclass
class BrightnessConfig:
    day: int = 60
    night: int = 15
    night_start: time = time(22, 30)
    night_end: time = time(7, 0)


@dataclass
class PollingConfig:
    live_seconds: float = 30
    idle_seconds: float = 300
    overnight_seconds: float = 3600
    overnight_start: time = time(1, 0)
    overnight_end: time = time(8, 0)
    timeout_seconds: float = 10
    max_backoff_seconds: float = 900


@dataclass
class LogoConfig:
    cache_dir: Path = Path("~/.cache/sportsticker/logos").expanduser()
    max_age_days: int = 30


@dataclass
class Config:
    timezone: str = "America/New_York"
    leagues: list[str] = field(default_factory=lambda: ["nfl"])  # enabled, in order
    favorites: dict[str, list[str]] = field(default_factory=dict)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    brightness: BrightnessConfig = field(default_factory=BrightnessConfig)
    polling: PollingConfig = field(default_factory=PollingConfig)
    logos: LogoConfig = field(default_factory=LogoConfig)
    matrix: dict[str, Any] = field(default_factory=dict)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def is_favorite(self, league: str, abbr: str) -> bool:
        return abbr.upper() in self.favorites.get(league, ())


def in_window(now: time, start: time, end: time) -> bool:
    """True if `now` falls in [start, end), where the window may wrap midnight."""
    if start <= end:
        return start <= now < end
    return now >= start or now < end


_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


class _Reader:
    """Pulls typed values out of a nested mapping, recording problems."""

    def __init__(self) -> None:
        self.problems: list[str] = []

    def section(self, raw: dict, name: str) -> dict:
        val = raw.get(name, {})
        if val is None:
            return {}
        if not isinstance(val, dict):
            self.problems.append(f"'{name}' must be a mapping")
            return {}
        return val

    def unknown(self, raw: dict, known: set[str], where: str) -> None:
        for key in raw:
            if key not in known:
                self.problems.append(f"unknown key '{where}{key}'")

    def num(self, raw, key, default, where, lo=None, hi=None, integer=False):
        val = raw.get(key, default)
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            self.problems.append(f"'{where}{key}' must be a number, got {val!r}")
            return default
        if integer and not float(val).is_integer():
            self.problems.append(f"'{where}{key}' must be a whole number, got {val!r}")
            return default
        if lo is not None and val < lo:
            self.problems.append(f"'{where}{key}' must be >= {lo}, got {val}")
            return default
        if hi is not None and val > hi:
            self.problems.append(f"'{where}{key}' must be <= {hi}, got {val}")
            return default
        return int(val) if integer else val

    def boolean(self, raw, key, default, where):
        val = raw.get(key, default)
        if not isinstance(val, bool):
            self.problems.append(f"'{where}{key}' must be true or false, got {val!r}")
            return default
        return val

    def choice(self, raw, key, default, choices, where):
        val = raw.get(key, default)
        val = str(val).lower() if val is not None else val
        if val not in choices:
            self.problems.append(f"'{where}{key}' must be one of {', '.join(choices)}, got {val!r}")
            return default
        return val

    def clock(self, raw, key, default: time, where) -> time:
        val = raw.get(key)
        if val is None:
            return default
        if isinstance(val, int):  # YAML 1.1 reads unquoted 22:30 as base-60 int
            val = f"{val // 60}:{val % 60:02d}"
        m = _TIME_RE.match(str(val).strip())
        if not m:
            self.problems.append(f"'{where}{key}' must be a time like \"22:30\", got {val!r}")
            return default
        return time(int(m.group(1)), int(m.group(2)))


def parse_config(raw: dict | None) -> Config:
    raw = raw or {}
    r = _Reader()
    if not isinstance(raw, dict):
        raise ConfigError(["config file must be a YAML mapping"])
    r.unknown(
        raw,
        {"timezone", "leagues", "favorites", "display", "brightness", "polling", "logos", "matrix"},
        "",
    )
    cfg = Config()

    # timezone
    tz = raw.get("timezone", cfg.timezone)
    try:
        ZoneInfo(str(tz))
        cfg.timezone = str(tz)
    except (ZoneInfoNotFoundError, ValueError):
        r.problems.append(f"'timezone' is not a known IANA zone: {tz!r}")

    # leagues: mapping of key -> bool, in display order
    leagues = raw.get("leagues", {"nfl": True})
    if isinstance(leagues, list):  # also accept a plain list of enabled keys
        leagues = {k: True for k in leagues}
    if not isinstance(leagues, dict):
        r.problems.append("'leagues' must map league keys to true/false")
        leagues = {}
    enabled = []
    for key, on in leagues.items():
        if key not in LEAGUES:
            r.problems.append(f"unknown league '{key}' (known: {', '.join(LEAGUES)})")
        elif not isinstance(on, bool):
            r.problems.append(f"'leagues.{key}' must be true or false")
        elif on:
            enabled.append(key)
    if not enabled and not r.problems:
        r.problems.append("no leagues enabled")
    cfg.leagues = enabled

    # favorites
    favs = r.section(raw, "favorites")
    for key, teams in favs.items():
        if key not in LEAGUES:
            r.problems.append(f"'favorites.{key}': unknown league")
            continue
        if isinstance(teams, str):
            teams = [teams]
        if not isinstance(teams, list) or not all(isinstance(t, str) for t in teams):
            r.problems.append(f"'favorites.{key}' must be a list of team abbreviations")
            continue
        cfg.favorites[key] = [t.strip().upper() for t in teams]

    # display
    d = r.section(raw, "display")
    w = "display."
    r.unknown(d, set(DisplayConfig.__dataclass_fields__), w)
    cfg.display = DisplayConfig(
        layout=r.choice(d, "layout", "a", LAYOUTS, w),
        logo_variant=r.choice(d, "logo_variant", "auto", LOGO_VARIANTS, w),
        logos=r.boolean(d, "logos", True, w),
        slide_seconds=r.num(d, "slide_seconds", 6, w, lo=1, hi=600),
        favorite_live_seconds=r.num(d, "favorite_live_seconds", 10, w, lo=1, hi=600),
        score_flash_seconds=r.num(d, "score_flash_seconds", 4, w, lo=0, hi=60),
        show_situation=r.boolean(d, "show_situation", True, w),
        transitions=r.boolean(d, "transitions", True, w),
        transition_style=r.choice(d, "transition_style", "push", TRANSITION_STYLES, w),
        transition_ms=r.num(d, "transition_ms", 400, w, lo=50, hi=5000, integer=True),
        animation_fps=r.num(d, "animation_fps", 30, w, lo=1, hi=120, integer=True),
    )

    # brightness
    b = r.section(raw, "brightness")
    w = "brightness."
    r.unknown(b, set(BrightnessConfig.__dataclass_fields__), w)
    cfg.brightness = BrightnessConfig(
        day=r.num(b, "day", 60, w, lo=0, hi=100, integer=True),
        night=r.num(b, "night", 15, w, lo=0, hi=100, integer=True),
        night_start=r.clock(b, "night_start", time(22, 30), w),
        night_end=r.clock(b, "night_end", time(7, 0), w),
    )

    # polling
    p = r.section(raw, "polling")
    w = "polling."
    r.unknown(p, set(PollingConfig.__dataclass_fields__), w)
    cfg.polling = PollingConfig(
        live_seconds=r.num(p, "live_seconds", 30, w, lo=MIN_POLL_SECONDS),
        idle_seconds=r.num(p, "idle_seconds", 300, w, lo=MIN_POLL_SECONDS),
        overnight_seconds=r.num(p, "overnight_seconds", 3600, w, lo=MIN_POLL_SECONDS),
        overnight_start=r.clock(p, "overnight_start", time(1, 0), w),
        overnight_end=r.clock(p, "overnight_end", time(8, 0), w),
        timeout_seconds=r.num(p, "timeout_seconds", 10, w, lo=1, hi=120),
        max_backoff_seconds=r.num(p, "max_backoff_seconds", 900, w, lo=MIN_POLL_SECONDS),
    )

    # logos
    lg = r.section(raw, "logos")
    w = "logos."
    r.unknown(lg, set(LogoConfig.__dataclass_fields__), w)
    cache = lg.get("cache_dir", "~/.cache/sportsticker/logos")
    cfg.logos = LogoConfig(
        cache_dir=Path(str(cache)).expanduser(),
        max_age_days=r.num(lg, "max_age_days", 30, w, lo=1, integer=True),
    )

    # matrix options: pass-through, type-checked
    m = r.section(raw, "matrix")
    for key, val in m.items():
        want = MATRIX_OPTIONS.get(key)
        if want is None:
            r.problems.append(f"unknown matrix option 'matrix.{key}'")
        elif want is int and (isinstance(val, bool) or not isinstance(val, int)):
            r.problems.append(f"'matrix.{key}' must be a whole number, got {val!r}")
        elif want is not int and not isinstance(val, want):
            r.problems.append(f"'matrix.{key}' must be {want.__name__}, got {val!r}")
        else:
            cfg.matrix[key] = val
    cfg.matrix.setdefault("rows", 32)
    cfg.matrix.setdefault("cols", 64)

    if r.problems:
        raise ConfigError(r.problems)
    return cfg


def load_config(path: str | Path) -> Config:
    path = Path(path)
    try:
        text = path.read_text()
    except FileNotFoundError:
        raise ConfigError([f"config file not found: {path}"]) from None
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ConfigError([f"{path} is not valid YAML: {e}"]) from None
    return parse_config(raw)
