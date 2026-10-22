from datetime import time

import pytest
from PIL import Image

from sportsticker.bdf import load_font
from sportsticker.colors import WHITE, luminance, team_color
from sportsticker.config import ConfigError, in_window, load_config, parse_config


def test_repo_config_is_valid():
    cfg = load_config("config.yaml")
    assert cfg.leagues == ["nfl", "ncaaf", "nba", "ncaab", "nhl", "epl"]
    assert cfg.is_favorite("nfl", "kc")
    assert cfg.matrix["hardware_mapping"] == "adafruit-hat"


def test_config_collects_all_problems():
    with pytest.raises(ConfigError) as e:
        parse_config(
            {
                "leagues": {"nfl": True, "xfl": True},
                "display": {"layout": "z", "slide_seconds": -1},
                "polling": {"live_seconds": 5},
                "matrix": {"rows": "32", "bogus": 1},
            }
        )
    msg = str(e.value)
    for needle in ("xfl", "layout", "slide_seconds", "live_seconds", "matrix.rows", "bogus"):
        assert needle in msg


def test_team_labels_default_to_top_and_are_validated():
    assert parse_config({"leagues": ["nfl"]}).display.team_labels == "top"
    cfg = parse_config({"leagues": ["nfl"], "display": {"team_labels": "center"}})
    assert cfg.display.team_labels == "center"
    with pytest.raises(ConfigError, match="team_labels"):
        parse_config({"leagues": ["nfl"], "display": {"team_labels": "side"}})


def test_unquoted_yaml_time_is_accepted():
    cfg = parse_config({"leagues": ["nfl"], "brightness": {"night_start": 22 * 60 + 30}})
    assert cfg.brightness.night_start == time(22, 30)


def test_window_wraps_midnight():
    assert in_window(time(23, 0), time(22, 30), time(7, 0))
    assert in_window(time(6, 59), time(22, 30), time(7, 0))
    assert not in_window(time(12, 0), time(22, 30), time(7, 0))


def test_font_renders_digits():
    f = load_font("5x7")
    assert f.text_width("10") == 10
    img = Image.new("RGB", (20, 10))
    f.draw(img, 0, 0, "1", WHITE)
    assert img.getbbox() is not None


def test_dark_team_colors_are_lifted():
    # Raiders: black / silver -> readable gray/white, never black
    assert luminance(team_color("000000", "a5acaf")) > 0.4
    # Bears: navy primary, orange alternate -> picks something visible
    assert luminance(team_color("0b1c3a", "e64100")) > 0.3
    assert team_color(None, None) == WHITE
