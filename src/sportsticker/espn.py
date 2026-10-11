"""ESPN scoreboard client and parser.

The scoreboard endpoint is undocumented, so everything here is defensive:
`parse_scoreboard` never raises, whatever it is given. An event that lacks the
essentials is skipped (with a debug log line) and the rest are kept.

Status mapping (ESPN `status.type`):
  * state "pre" / "in" / "post" map straight through.
  * Any other / missing state falls back on `completed` and the status name
    (FINAL, FULL_TIME, ... -> "post"; IN_PROGRESS, HALFTIME, ... -> "in"),
    and otherwise defaults to "pre".
  * Postponed / canceled games (status name contains POSTPONED or CANCELED/
    CANCELLED) are kept with state "post" (they will not be played today, and
    "post" keeps them out of the live/upcoming groups), `completed=False`,
    scores None, and `short_detail` set to ESPN's detail ("Postponed",
    "Canceled", ...). `extra["status_name"]` carries ESPN's raw status name
    (e.g. "STATUS_POSTPONED") so a renderer can tell them from real finals.
  * Delayed / suspended games keep ESPN's own state (normally "in").
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from .models import LEAGUES, Competitor, Game, League, Situation, State, Team

log = logging.getLogger(__name__)

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard"
USER_AGENT = "sportsticker/0.1 (+LED matrix scoreboard; personal use)"

# ESPN groups ids: 80 = FBS (all), 50 = NCAA Division I (all).
_COLLEGE_PARAMS: dict[str, dict[str, str]] = {
    "ncaaf": {"groups": "80", "limit": "300"},
    "ncaab": {"groups": "50", "limit": "400"},
}

_HEX_RE = re.compile(r"^[0-9a-fA-F]{6}$")


def query_params(league_key: str) -> dict[str, str]:
    """Extra query string for a league's scoreboard (all-games college boards)."""
    return dict(_COLLEGE_PARAMS.get(league_key, {}))


# ---------------------------------------------------------------- helpers


def _s(value: Any) -> str:
    """Best-effort string: str/int -> str, anything else -> ''."""
    if isinstance(value, bool):
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(int(value)) if float(value).is_integer() else str(value)
    return ""


def _int(value: Any) -> int | None:
    """Parse ints from ints, floats, numeric strings and {'value'/'displayValue'} dicts."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, dict):
        for k in ("value", "displayValue"):
            if k in value:
                got = _int(value[k])
                if got is not None:
                    return got
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value == value and abs(value) != float("inf") else None
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except (ValueError, OverflowError):
            return None
    return None


def _hex(value: Any) -> str | None:
    text = _s(value).lstrip("#")
    return text.lower() if _HEX_RE.match(text) else None


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def parse_date(value: Any) -> datetime | None:
    """ESPN dates look like '2026-10-11T17:00Z' (no seconds) or with seconds."""
    text = _s(value)
    if not text:
        return None
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _logo_urls(team: dict) -> tuple[str | None, str | None]:
    logo = _s(team.get("logo")) or None
    dark = _s(team.get("logoDark")) or None
    logos = team.get("logos")
    if isinstance(logos, list):
        for entry in logos:
            entry = _dict(entry)
            href = _s(entry.get("href"))
            rel = entry.get("rel")
            rels = [r for r in rel if isinstance(r, str)] if isinstance(rel, list) else []
            if not href:
                continue
            if any("dark" in r.lower() for r in rels):
                dark = dark or href
            else:
                logo = logo or href
    return logo, dark


def _parse_team(raw: dict, abbr: str) -> Team:
    team = _dict(raw.get("team"))
    logo, dark = _logo_urls(team)
    return Team(
        abbr=abbr,
        name=_s(team.get("shortDisplayName")) or _s(team.get("name")),
        color=_hex(team.get("color")),
        alt_color=_hex(team.get("alternateColor")),
        logo_url=logo,
        logo_dark_url=dark,
        id=_s(team.get("id")) or _s(raw.get("id")),
    )


def _parse_competitor(raw: dict, abbr: str, home: bool) -> Competitor:
    rank = _int(_dict(raw.get("curatedRank")).get("current"))
    if rank is not None and not 1 <= rank <= 25:
        rank = None
    return Competitor(
        team=_parse_team(raw, abbr), home=home, score=_int(raw.get("score")), rank=rank
    )


def _parse_status(event: dict, comp: dict) -> tuple[State, str, str, int, bool, str]:
    """-> (state, short_detail, display_clock, period, completed, status_name)."""
    status = _dict(event.get("status")) or _dict(comp.get("status"))
    stype = _dict(status.get("type"))
    name = _s(stype.get("name")).upper()
    raw_state = _s(stype.get("state")).lower()
    completed = stype.get("completed") is True
    short = _s(stype.get("shortDetail")) or _s(stype.get("detail"))
    clock = _s(status.get("displayClock"))
    period = _int(status.get("period")) or 0

    if "POSTPONED" in name or "CANCEL" in name:
        detail = short or _s(stype.get("description"))
        if not detail:
            detail = "Postponed" if "POSTPONED" in name else "Canceled"
        return "post", detail, "", 0, False, name

    state: State
    if raw_state in ("pre", "in", "post"):
        state = raw_state  # type: ignore[assignment]
    elif completed or any(k in name for k in ("FINAL", "FULL_TIME", "FORFEIT", "ABANDON")):
        state = "post"
    elif any(k in name for k in ("PROGRESS", "HALF", "END_PERIOD", "DELAY", "SUSPEND")):
        state = "in"
    else:
        state = "pre"
    if state == "post" and not completed and "FINAL" in name:
        completed = True
    return state, short, clock, max(period, 0), completed, name


def _parse_situation(comp: dict) -> Situation | None:
    raw = comp.get("situation")
    if not isinstance(raw, dict) or not raw:
        return None
    possession = _s(raw.get("possession")) or None
    down = _s(raw.get("downDistanceText")) or None
    short = _s(raw.get("shortDownDistanceText")) or None
    red = raw.get("isRedZone") is True
    if possession is None and down is None and short is None and not red:
        return None
    return Situation(
        possession_team_id=possession,
        down_distance=down,
        short_down_distance=short,
        red_zone=red,
    )


def _parse_event(event: Any, league_key: str) -> Game | None:
    event = _dict(event)
    game_id = _s(event.get("id"))
    if not game_id:
        log.debug("skip event without id")
        return None
    comps = event.get("competitions")
    comp = _dict(comps[0]) if isinstance(comps, list) and comps else {}
    competitors = comp.get("competitors")
    if not isinstance(competitors, list):
        log.debug("skip event %s: no competitors", game_id)
        return None

    sides: dict[str, tuple[dict, str]] = {}
    for raw in competitors:
        raw = _dict(raw)
        side = _s(raw.get("homeAway")).lower()
        abbr = _s(_dict(raw.get("team")).get("abbreviation"))
        if side in ("home", "away") and abbr and side not in sides:
            sides[side] = (raw, abbr)
    if len(sides) != 2:
        log.debug("skip event %s: need a home and an away competitor with abbreviations", game_id)
        return None

    start = (
        parse_date(event.get("date"))
        or parse_date(comp.get("date"))
        or parse_date(comp.get("startDate"))
    )
    if start is None:
        log.debug("skip event %s: no parseable start date", game_id)
        return None

    state, short, clock, period, completed, status_name = _parse_status(event, comp)
    away = _parse_competitor(*sides["away"], home=False)
    home = _parse_competitor(*sides["home"], home=True)
    if status_name and ("POSTPONED" in status_name or "CANCEL" in status_name):
        away = Competitor(away.team, False, None, away.rank)
        home = Competitor(home.team, True, None, home.rank)

    return Game(
        id=game_id,
        league=league_key,
        state=state,
        start=start,
        away=away,
        home=home,
        short_detail=short,
        display_clock=clock,
        period=period,
        completed=completed,
        situation=_parse_situation(comp) if state == "in" else None,
        extra={"status_name": status_name} if status_name else {},
    )


# ------------------------------------------------------------------ public


def parse_scoreboard(data: Any, league_key: str) -> list[Game]:
    """Turn a raw scoreboard payload into Games. Never raises."""
    try:
        events = data.get("events") if isinstance(data, dict) else None
        if not isinstance(events, list):
            log.debug("scoreboard for %s has no events list", league_key)
            return []
        games: list[Game] = []
        seen: set[str] = set()
        for event in events:
            try:
                game = _parse_event(event, league_key)
            except Exception as exc:  # defensive: one bad event must not cost the rest
                log.debug("skip event in %s: %r", league_key, exc)
                continue
            if game is None or game.id in seen:
                continue
            seen.add(game.id)
            games.append(game)
        return games
    except Exception as exc:
        log.debug("parse_scoreboard(%s) failed: %r", league_key, exc)
        return []


def ticker_day(moment: datetime, tz: ZoneInfo, rollover_hour: int = 4):
    """The 'ticker day' (a date) `moment` belongs to: days roll over at rollover_hour local."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return (moment.astimezone(tz) - timedelta(hours=rollover_hour)).date()


def filter_today(
    games: list[Game], now: datetime, tz: ZoneInfo, rollover_hour: int = 4
) -> list[Game]:
    """Keep games starting on the current ticker day, plus anything in progress.

    The day boundary is `rollover_hour` local time, so a game that began at
    10 PM is still shown at 1 AM, and tomorrow's early game is not shown yet.
    """
    today = ticker_day(now, tz, rollover_hour)
    return [g for g in games if g.state == "in" or ticker_day(g.start, tz, rollover_hour) == today]


def college_filter(games: list[Game], favorites: list[str]) -> list[Game]:
    """Keep games with a ranked (1..25) team or a favorite team."""
    favs = {f.strip().upper() for f in favorites if isinstance(f, str)}

    def keep(g: Game) -> bool:
        for c in (g.away, g.home):
            if c.rank is not None and 1 <= c.rank <= 25:
                return True
            if c.team.abbr.upper() in favs:
                return True
        return False

    return [g for g in games if keep(g)]


def fetch_scoreboard(league: League, session: requests.Session, timeout: float) -> dict:
    """GET one league's scoreboard JSON. Raises on network, HTTP or shape errors."""
    url = SCOREBOARD_URL.format(sport=league.sport, league=league.league)
    resp = session.get(
        url,
        params=query_params(league.key),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError(f"unexpected scoreboard payload ({type(data).__name__})")
    return data


def save_fixtures(
    league_keys: list[str],
    out_dir: Path,
    session: requests.Session | None = None,
    timeout: float = 20.0,
) -> list[Path]:
    """Fetch each league's raw JSON (with college params) into {sport}_{league}.json.

    Each fetch is retried once; a league that still fails raises.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    own = session is None
    sess = session or requests.Session()
    paths: list[Path] = []
    try:
        for key in league_keys:
            league = LEAGUES[key]
            try:
                data = fetch_scoreboard(league, sess, timeout)
            except (requests.RequestException, ValueError) as exc:
                log.warning("fetch %s failed (%s); retrying once", key, exc)
                time.sleep(1)
                data = fetch_scoreboard(league, sess, timeout)
            path = out_dir / f"{league.sport}_{league.league}.json"
            path.write_text(json.dumps(data, separators=(",", ":")))
            paths.append(path)
    finally:
        if own:
            sess.close()
    return paths


if __name__ == "__main__":  # python -m sportsticker.espn OUT_DIR [league ...]
    import sys

    logging.basicConfig(level=logging.INFO)
    target = Path(sys.argv[1])
    keys = sys.argv[2:] or list(LEAGUES)
    for p in save_fixtures(keys, target):
        print(p)
