"""ESPN parser, filters and fixture helpers. No network."""

from __future__ import annotations

import copy
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from sportsticker import espn
from sportsticker.models import LEAGUES, Competitor, Game, Team

FIXTURES = Path(__file__).parent / "fixtures" / "2026-10-11-sun"
NY = ZoneInfo("America/New_York")


def load(name: str):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(scope="module")
def nfl_raw():
    return load("football_nfl.json")


@pytest.fixture(scope="module")
def nfl(nfl_raw):
    return espn.parse_scoreboard(nfl_raw, "nfl")


def by_id(games, gid):
    return next(g for g in games if g.id == gid)


# ------------------------------------------------------------------ parsing


@pytest.mark.parametrize(
    ("file", "key", "count"),
    [
        ("football_nfl.json", "nfl", 15),
        ("basketball_nba.json", "nba", 4),
        ("hockey_nhl.json", "nhl", 3),
        ("soccer_eng.1.json", "epl", 3),
        ("football_college-football.json", "ncaaf", 58),
        ("basketball_mens-college-basketball.json", "ncaab", 2),
    ],
)
def test_fixture_counts(file, key, count):
    games = espn.parse_scoreboard(load(file), key)
    assert len(games) == count
    assert all(g.league == key for g in games)
    assert len({g.id for g in games}) == count
    for g in games:
        assert g.start.tzinfo is not None
        assert g.start.utcoffset() == timedelta(0)
        assert g.away.team.abbr and g.home.team.abbr
        assert g.away.home is False and g.home.home is True


def test_nfl_states(nfl):
    states = [g.state for g in nfl]
    assert states.count("in") == 8
    assert states.count("pre") == 5
    assert states.count("post") == 2


def test_known_live_game(nfl):
    g = by_id(nfl, "401872990")  # GB (home) vs CHI (away)
    assert g.state == "in"
    assert g.home.team.abbr == "GB" and g.away.team.abbr == "CHI"
    assert (g.home.score, g.away.score) == (20, 7)
    assert g.home.team.name == "Packers"
    assert g.home.team.id == "9"
    assert g.home.team.color == "204e32"
    assert g.home.team.alt_color == "ffb612"
    assert g.home.team.logo_url.endswith("/nfl/500/scoreboard/gb.png")
    assert g.home.team.logo_dark_url.endswith("/nfl/500-dark/scoreboard/gb.png")
    assert g.short_detail == "8:01 - 3rd"
    assert g.display_clock == "8:01"
    assert g.period == 3
    assert g.completed is False
    assert g.start == datetime(2026, 10, 11, 17, 0, tzinfo=UTC)
    # 99 means unranked in ESPN's curatedRank
    assert g.home.rank is None and g.away.rank is None


def test_live_nfl_game_has_situation(nfl):
    g = by_id(nfl, "401872990")
    s = g.situation
    assert s is not None
    assert s.possession_team_id == "9"
    assert s.down_distance == "3rd & 2 at GB 41"
    assert s.short_down_distance == "3rd & 2"
    assert s.red_zone is False
    assert g.competitor_for(s.possession_team_id) is g.home
    assert all(x.situation is not None for x in nfl if x.state == "in")


def test_pre_and_post_games(nfl):
    pre = by_id(nfl, "401872989")  # DEN @ LAC
    assert pre.state == "pre" and pre.situation is None
    assert pre.short_detail == "10/11 - 4:05 PM EDT"
    assert pre.start == datetime(2026, 10, 11, 20, 5, tzinfo=UTC)
    post = by_id(nfl, "401872981")  # PHI @ JAX
    assert post.state == "post" and post.completed is True and post.situation is None
    assert post.short_detail == "Final"
    assert (post.home.score, post.away.score) == (19, 17)


def test_situation_only_for_live_games(nfl_raw):
    raw = copy.deepcopy(nfl_raw)
    # copy a live situation onto a pre game: must be ignored
    live = next(e for e in raw["events"] if e["status"]["type"]["state"] == "in")
    pre = next(e for e in raw["events"] if e["status"]["type"]["state"] == "pre")
    pre["competitions"][0]["situation"] = live["competitions"][0]["situation"]
    games = espn.parse_scoreboard(raw, "nfl")
    assert by_id(games, pre["id"]).situation is None


def test_college_ranks():
    games = espn.parse_scoreboard(load("football_college-football.json"), "ncaaf")
    ranked = [c for g in games for c in (g.away, g.home) if c.rank is not None]
    assert ranked
    assert all(1 <= c.rank <= 25 for c in ranked)
    byu = next(g for g in games if g.away.team.abbr == "ISU" and g.home.team.abbr == "BYU")
    assert byu.home.rank == 8 and byu.away.rank is None
    tex = next(g for g in games if g.away.team.abbr == "TEX")
    assert tex.away.rank == 1 and tex.home.rank is None
    uga = next(g for g in games if g.away.team.abbr == "UGA")
    assert (uga.away.rank, uga.home.rank) == (2, 6)


def test_soccer_final_detail():
    games = espn.parse_scoreboard(load("soccer_eng.1.json"), "epl")
    assert all(g.state == "post" for g in games)
    assert games[0].short_detail == "FT"


def test_parse_dates():
    p = espn.parse_date
    assert p("2026-10-11T17:00Z") == datetime(2026, 10, 11, 17, 0, tzinfo=UTC)
    assert p("2026-10-11T17:00:30Z") == datetime(2026, 10, 11, 17, 0, 30, tzinfo=UTC)
    assert p("2026-10-11T13:00-04:00") == datetime(2026, 10, 11, 17, 0, tzinfo=UTC)
    assert p("2026-10-11T17:00") == datetime(2026, 10, 11, 17, 0, tzinfo=UTC)
    for bad in ("", None, 5, "soon", "2026-13-45T00:00Z", []):
        assert p(bad) is None


def _event(**over):
    ev = {
        "id": "1",
        "date": "2026-10-11T17:00Z",
        "status": {
            "displayClock": "0:00",
            "period": 0,
            "type": {"state": "pre", "shortDetail": "10/11 - 1:00 PM EDT", "completed": False},
        },
        "competitions": [
            {
                "competitors": [
                    {"homeAway": "home", "score": "0", "team": {"id": "1", "abbreviation": "AAA"}},
                    {"homeAway": "away", "score": "0", "team": {"id": "2", "abbreviation": "BBB"}},
                ]
            }
        ],
    }
    ev.update(over)
    return ev


def test_minimal_event_parses():
    (g,) = espn.parse_scoreboard({"events": [_event()]}, "nfl")
    assert g.home.team == Team(abbr="AAA", name="", id="1")
    assert g.state == "pre" and g.home.score == 0


def test_string_and_odd_scores():
    ev = _event()
    comps = ev["competitions"][0]["competitors"]
    comps[0]["score"] = "21"
    comps[1]["score"] = {"displayValue": "7"}
    (g,) = espn.parse_scoreboard({"events": [ev]}, "nfl")
    assert (g.home.score, g.away.score) == (21, 7)
    comps[0]["score"] = "n/a"
    comps[1]["score"] = None
    (g,) = espn.parse_scoreboard({"events": [ev]}, "nfl")
    assert g.home.score is None and g.away.score is None
    comps[0]["score"] = 3.0
    comps[1]["score"] = True
    (g,) = espn.parse_scoreboard({"events": [ev]}, "nfl")
    assert g.home.score == 3 and g.away.score is None


def test_logo_dark_from_logos_list():
    ev = _event()
    ev["competitions"][0]["competitors"][0]["team"].update(
        {
            "logo": "https://x/light.png",
            "logos": [
                {"href": "https://x/default.png", "rel": ["full", "default"]},
                {"href": "https://x/dark.png", "rel": ["full", "dark"]},
            ],
        }
    )
    (g,) = espn.parse_scoreboard({"events": [ev]}, "nfl")
    assert g.home.team.logo_url == "https://x/light.png"
    assert g.home.team.logo_dark_url == "https://x/dark.png"


def test_bad_colors_ignored_and_rank_bounds():
    ev = _event()
    comps = ev["competitions"][0]["competitors"]
    comps[0]["team"].update({"color": "#ABCDEF", "alternateColor": "zzz"})
    comps[0]["curatedRank"] = {"current": 25}
    comps[1]["curatedRank"] = {"current": 26}
    (g,) = espn.parse_scoreboard({"events": [ev]}, "ncaaf")
    assert g.home.team.color == "abcdef" and g.home.team.alt_color is None
    assert g.home.rank == 25 and g.away.rank is None
    comps[0]["curatedRank"] = {"current": 0}
    (g,) = espn.parse_scoreboard({"events": [ev]}, "ncaaf")
    assert g.home.rank is None


@pytest.mark.parametrize(
    ("type_", "state", "completed"),
    [
        ({"state": "weird"}, "pre", False),
        ({}, "pre", False),
        ({"state": "weird", "completed": True}, "post", True),
        ({"name": "STATUS_FINAL"}, "post", True),
        ({"name": "STATUS_HALFTIME"}, "in", False),
        ({"state": "IN", "name": "STATUS_IN_PROGRESS"}, "in", False),
    ],
)
def test_state_mapping(type_, state, completed):
    ev = _event()
    ev["status"]["type"] = type_
    (g,) = espn.parse_scoreboard({"events": [ev]}, "nfl")
    assert g.state == state and g.completed is completed


@pytest.mark.parametrize(
    ("name", "detail", "expect"),
    [
        ("STATUS_POSTPONED", "Postponed", "Postponed"),
        ("STATUS_CANCELED", "Canceled", "Canceled"),
        ("STATUS_POSTPONED", "", "Postponed"),
        ("STATUS_CANCELLED", "", "Canceled"),
    ],
)
def test_postponed_and_canceled(name, detail, expect):
    ev = _event()
    ev["status"]["type"] = {"name": name, "state": "pre", "shortDetail": detail}
    (g,) = espn.parse_scoreboard({"events": [ev]}, "nfl")
    assert g.state == "post" and g.completed is False
    assert g.short_detail == expect
    assert g.extra["status_name"] == name
    assert g.home.score is None and g.away.score is None


def test_skips_bad_events_keeps_good():
    bad = [
        None,
        "str",
        42,
        {},
        _event(id=None),
        _event(id=""),
        _event(competitions=[]),
        _event(competitions=None),
        _event(date="garbage"),
        _event(date=None),
    ]
    one_side = _event()
    one_side["competitions"][0]["competitors"].pop()
    no_abbr = _event()
    no_abbr["competitions"][0]["competitors"][0]["team"]["abbreviation"] = ""
    same_side = _event()
    same_side["competitions"][0]["competitors"][1]["homeAway"] = "home"
    good = _event(id="99")
    games = espn.parse_scoreboard(
        {"events": [*bad, one_side, no_abbr, same_side, good, copy.deepcopy(good)]}, "nfl"
    )
    assert [g.id for g in games] == ["99"]  # duplicate id dropped too


def test_int_event_id_is_accepted():
    (g,) = espn.parse_scoreboard({"events": [_event(id=12345)]}, "nfl")
    assert g.id == "12345"


@pytest.mark.parametrize(
    "data",
    [None, [], "x", 5, 1.5, True, {}, {"events": None}, {"events": {}}, {"events": "x"}, [[], {}]],
)
def test_parse_never_raises_on_garbage(data):
    assert espn.parse_scoreboard(data, "nfl") == []


def _paths(node, prefix=()):
    yield prefix
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _paths(v, (*prefix, k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _paths(v, (*prefix, i))


def _get(node, path):
    for p in path:
        node = node[p]
    return node


JUNK = [None, "", "abc", 0, -1, 3.5, True, [], {}, [1, 2], {"a": 1}, "2026-99-99", 10**30]


def test_fuzz_never_raises(nfl_raw):
    rng = random.Random(1234)
    # keep the fuzzed document small so 200 rounds stay fast, but keep all event kinds
    base = copy.deepcopy(nfl_raw)
    base.pop("leagues", None)
    noise = ("links", "leaders", "notes", "broadcasts", "geoBroadcasts", "highlights", "venue")
    noise += ("weather", "statistics", "records", "linescores", "tickets", "odds")
    for e in base["events"]:
        for node in (e, e["competitions"][0], *e["competitions"][0]["competitors"]):
            for k in noise:
                node.pop(k, None)
            if isinstance(node.get("team"), dict):
                node["team"].pop("links", None)
                node["team"].pop("venue", None)
        e["competitions"][0].get("situation", {}).pop("lastPlay", None)
    base["events"] = [
        e
        for e in base["events"]
        if e["status"]["type"]["state"] != "in" or e["id"] in ("401872990", "401872984")
    ]
    for _ in range(200):
        doc = copy.deepcopy(base)
        for _ in range(rng.randint(1, 25)):
            paths = [p for p in _paths(doc) if p]
            path = rng.choice(paths)
            try:
                parent = _get(doc, path[:-1])
                key = path[-1]
                if rng.random() < 0.5:
                    del parent[key]
                else:
                    parent[key] = copy.deepcopy(rng.choice(JUNK))
            except (KeyError, IndexError, TypeError):
                continue
        games = espn.parse_scoreboard(doc, "nfl")
        assert isinstance(games, list)
        assert all(isinstance(g, Game) for g in games)


def test_fuzz_college_and_soccer_never_raise():
    rng = random.Random(99)
    for file in ("football_college-football.json", "soccer_eng.1.json"):
        base = load(file)
        base["events"] = base["events"][:4]
        for _ in range(50):
            doc = copy.deepcopy(base)
            for _ in range(rng.randint(1, 15)):
                path = rng.choice([p for p in _paths(doc) if p])
                try:
                    _get(doc, path[:-1])[path[-1]] = copy.deepcopy(rng.choice(JUNK))
                except (KeyError, IndexError, TypeError):
                    continue
            espn.parse_scoreboard(doc, "ncaaf")


# ------------------------------------------------------------- filter_today


def mk_game(gid: str, start: datetime, state="pre", away="AWY", home="HOM", ranks=(None, None)):
    return Game(
        id=gid,
        league="nfl",
        state=state,
        start=start,
        away=Competitor(Team(abbr=away), False, None, ranks[0]),
        home=Competitor(Team(abbr=home), True, None, ranks[1]),
    )


def local(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=NY).astimezone(UTC)


def test_filter_today_real_nfl_board(nfl):
    # Sunday 2:00 PM Eastern
    kept = espn.filter_today(nfl, local(2026, 10, 11, 14), NY)
    ids = {g.id for g in kept}
    assert "401872980" not in ids  # Thursday night final
    assert "401872994" not in ids  # Monday night
    assert "401872993" in ids  # Sunday 8:20 PM EDT = 00:20Z Monday
    assert len(kept) == 13


def test_filter_today_rollover():
    late = mk_game("late", local(2026, 10, 11, 22), "post")  # 10 PM Sunday
    early = mk_game("early", local(2026, 10, 12, 13))  # Monday 1 PM
    old = mk_game("old", local(2026, 10, 10, 20), "post")  # Saturday
    games = [late, early, old]
    # Sunday 11 PM: late shown; Monday's game is not
    assert espn.filter_today(games, local(2026, 10, 11, 23), NY) == [late]
    # Monday 1 AM: still the Sunday ticker day
    assert espn.filter_today(games, local(2026, 10, 12, 1), NY) == [late]
    # Monday 3:59 AM: still Sunday; 4:00 AM rolls over
    assert espn.filter_today(games, local(2026, 10, 12, 3, 59), NY) == [late]
    assert espn.filter_today(games, local(2026, 10, 12, 4), NY) == [early]
    # Custom rollover hour
    assert espn.filter_today(games, local(2026, 10, 12, 1), NY, rollover_hour=0) == [early]


def test_filter_today_keeps_live_games_any_date():
    live = mk_game("live", local(2026, 10, 9, 20), "in")
    done = mk_game("done", local(2026, 10, 9, 20), "post")
    assert espn.filter_today([live, done], local(2026, 10, 11, 12), NY) == [live]


def test_filter_today_uses_tz_and_naive_now():
    g = mk_game("g", datetime(2026, 10, 12, 3, 0, tzinfo=UTC))  # Sun 11 PM NY, Mon noon Tokyo
    now = datetime(2026, 10, 11, 10, 0, tzinfo=UTC)  # 6 AM Sun in NY, 7 PM Sun in Tokyo
    assert espn.filter_today([g], now, NY) == [g]
    assert espn.filter_today([g], now, ZoneInfo("Asia/Tokyo")) == []
    assert espn.filter_today([g], datetime(2026, 10, 11, 10, 0), NY) == [g]  # naive = UTC


def test_filter_today_dst_boundary():
    # US fall-back is 2026-11-01; a 1 AM-ish game on that night must stay on Saturday's day
    g = mk_game("g", local(2026, 10, 31, 23))
    assert espn.filter_today([g], local(2026, 11, 1, 3), NY) == [g]
    assert espn.filter_today([g], local(2026, 11, 1, 5), NY) == []


# ----------------------------------------------------------- college params


def test_query_params():
    assert espn.query_params("ncaaf") == {"groups": "80", "limit": "300"}
    assert espn.query_params("ncaab") == {"groups": "50", "limit": "400"}
    for key in ("nfl", "nba", "nhl", "epl", "mlb", "unknown"):
        assert espn.query_params(key) == {}
    espn.query_params("ncaaf")["groups"] = "x"  # callers get a copy
    assert espn.query_params("ncaaf")["groups"] == "80"


def test_college_filter():
    t0 = local(2026, 10, 11, 12)
    ranked_home = mk_game("a", t0, home="UGA", ranks=(None, 3))
    ranked_away = mk_game("b", t0, away="ALA", ranks=(25, None))
    fav = mk_game("c", t0, away="CREI", home="XAV")
    fav_home = mk_game("d", t0, away="MIA", home="CREI")
    plain = mk_game("e", t0, away="TROY", home="USM")
    unranked_99 = mk_game("f", t0, ranks=(26, 0))
    games = [ranked_home, ranked_away, fav, fav_home, plain, unranked_99]
    out = espn.college_filter(games, ["crei"])
    assert [g.id for g in out] == ["a", "b", "c", "d"]
    assert [g.id for g in espn.college_filter(games, [])] == ["a", "b"]


def test_college_filter_on_real_data():
    games = espn.parse_scoreboard(load("football_college-football.json"), "ncaaf")
    assert len(games) == 58
    out = espn.college_filter(games, [])
    assert 0 < len(out) < len(games)
    assert all(1 <= c.rank <= 25 for g in out for c in (g.away, g.home) if c.rank)
    assert all(g.away.rank or g.home.rank for g in out)
    troy = espn.college_filter(games, ["TROY"])
    assert any(g.home.team.abbr == "TROY" or g.away.team.abbr == "TROY" for g in troy)


# --------------------------------------------------------------- fetching


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            import requests

            raise requests.HTTPError(f"{self.status} error")

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payloads=None, fail_first=0):
        self.calls: list[dict] = []
        self.payloads = payloads or {}
        self.fail_first = fail_first

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        if self.fail_first > 0:
            self.fail_first -= 1
            import requests

            raise requests.ConnectionError("boom")
        return FakeResponse(self.payloads.get(url, {"events": []}))

    def close(self):
        pass


def test_fetch_scoreboard_url_params_headers():
    s = FakeSession()
    espn.fetch_scoreboard(LEAGUES["ncaaf"], s, 7.5)
    call = s.calls[0]
    assert call["url"] == (
        "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"
    )
    assert call["params"] == {"groups": "80", "limit": "300"}
    assert call["timeout"] == 7.5
    assert "sportsticker" in call["headers"]["User-Agent"]
    espn.fetch_scoreboard(LEAGUES["nfl"], s, 5)
    assert s.calls[1]["params"] == {}


def test_fetch_scoreboard_rejects_bad_payload_and_status():
    import requests

    url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
    with pytest.raises(ValueError):
        espn.fetch_scoreboard(LEAGUES["nfl"], FakeSession({url: ["not", "a", "dict"]}), 5)

    class Err(FakeSession):
        def get(self, *a, **k):
            return FakeResponse({}, status=503)

    with pytest.raises(requests.HTTPError):
        espn.fetch_scoreboard(LEAGUES["nfl"], Err(), 5)


def test_save_fixtures_writes_named_files_and_retries(tmp_path, monkeypatch):
    monkeypatch.setattr(espn.time, "sleep", lambda s: None)
    s = FakeSession(fail_first=1)
    paths = espn.save_fixtures(["nfl", "ncaab"], tmp_path / "out", session=s)
    assert [p.name for p in paths] == [
        "football_nfl.json",
        "basketball_mens-college-basketball.json",
    ]
    assert all(json.loads(p.read_text()) == {"events": []} for p in paths)
    assert len(s.calls) == 3  # one retry
    assert s.calls[2]["params"] == {"groups": "50", "limit": "400"}


@pytest.mark.skip(reason="hits the network; run manually")
def test_live_college_groups():  # pragma: no cover
    import requests

    data = espn.fetch_scoreboard(LEAGUES["ncaaf"], requests.Session(), 20)
    assert espn.parse_scoreboard(data, "ncaaf")
