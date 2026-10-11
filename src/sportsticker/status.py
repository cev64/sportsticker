"""Short status text for a game: live clock and period, FINAL, or local start time."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from .models import LEAGUES, Game


@dataclass(frozen=True)
class Status:
    period: str  # "Q3", "2H", "P2", "OT", "HALF", "FINAL", "7:20"
    clock: str  # "4:12", "PM", "62'", "OT", ""
    detail: str = ""  # "3&7" (football down & distance), may be empty

    @property
    def line(self) -> str:
        """One-line form for layouts with a single status row."""
        if self.period == "FINAL" and self.clock:
            return f"FINAL/{self.clock}"
        return f"{self.period} {self.clock}".strip()


def _sport(game: Game) -> str:
    lg = LEAGUES.get(game.league)
    return lg.sport if lg else ""


def period_label(game: Game) -> str:
    sport, p = _sport(game), game.period
    if p <= 0:
        return ""
    if sport == "hockey":
        if p <= 3:
            return f"P{p}"
        return "SO" if p == 5 and "shootout" in game.short_detail.lower() else "OT"
    if game.league == "ncaab":  # men's college basketball plays halves
        return f"{p}H" if p <= 2 else ("OT" if p == 3 else f"{p - 2}OT")
    if sport in ("football", "basketball"):
        return f"Q{p}" if p <= 4 else ("OT" if p == 5 else f"{p - 4}OT")
    if sport == "baseball":
        half = "BOT" if "bot" in game.short_detail.lower() else "TOP"
        return f"{half} {p}"
    return ""


def start_time(game: Game, tz: ZoneInfo, now: datetime | None = None) -> tuple[str, str]:
    """('7:20', 'PM'), or ('SAT', '1:00P') when the game isn't today."""
    local = game.start.astimezone(tz)
    hour = local.hour % 12 or 12
    hm = f"{hour}:{local.minute:02d}"
    ampm = "AM" if local.hour < 12 else "PM"
    if now is not None and local.date() != now.astimezone(tz).date():
        return local.strftime("%a").upper(), f"{hm}{ampm[0]}"
    return hm, ampm


_DOWN = re.compile(r"^\s*([1-4])(?:st|nd|rd|th)?\s*(?:&|and)\s*(\w+)", re.I)


def compact_down(text: str) -> str:
    """'3rd & 10' -> '3&10', '1st & Goal' -> '1&G'; '' if unrecognised."""
    m = _DOWN.match(text or "")
    if not m:
        return ""
    dist = m.group(2)
    return f"{m.group(1)}&{'G' if dist.lower() == 'goal' else dist}"


_FINAL_SUFFIX = re.compile(r"final\s*/\s*(\w+)", re.I)


def game_status(game: Game, tz: ZoneInfo, now: datetime | None = None) -> Status:
    detail = (game.short_detail or "").strip()
    low = detail.lower()

    if "postpon" in low:
        return Status("PPD", "")
    if "cancel" in low:
        return Status("CNCL", "")
    if "delay" in low:
        return Status("DELAY", "")

    if game.state == "pre":
        if "tbd" in low:
            return Status("TBD", "")
        t, ampm = start_time(game, tz, now)
        return Status(t, ampm)

    if game.state == "post":
        m = _FINAL_SUFFIX.search(detail)
        return Status("FINAL", m.group(1).upper() if m else "")

    # live
    sport = _sport(game)
    football_detail = ""
    if sport == "football" and game.situation:
        football_detail = compact_down(
            game.situation.short_down_distance or game.situation.down_distance or ""
        )
    if "half" in low and "1st half" not in low and "2nd half" not in low:
        return Status("HALF", "", football_detail)
    if sport == "soccer":
        if low in ("ht", "halftime"):
            return Status("HALF", "")
        clock = game.display_clock or detail
        return Status(clock.replace(" ", ""), "")
    label = period_label(game)
    if low.startswith("end"):
        return Status("END", label)
    if sport == "baseball":
        return Status(label, "")
    clock = game.display_clock or ""
    if clock in ("0:00", "0.0", "00:00") and label:
        return Status("END", label, football_detail)
    return Status(label, clock, football_detail)
