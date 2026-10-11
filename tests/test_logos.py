"""LogoStore tests: synthetic PNGs and a fake HTTP session, no network, tmp_path only."""

import io
import os
import time

import pytest
from PIL import Image

from sportsticker import logos
from sportsticker.logos import LogoStore, prefetch, process_logo, readability, team_from_espn
from sportsticker.models import Team


def png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def solid(w, h, color, margin=0, size=None):
    """Opaque rectangle of `color` inside a transparent canvas."""
    cw, ch = size or (w + 2 * margin, h + 2 * margin)
    im = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    im.paste(Image.new("RGBA", (w, h), color + (255,)), (margin, margin))
    return im


class FakeResp:
    def __init__(self, content=b"", status=200):
        self.content, self.status_code = content, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, files: dict[str, bytes]):
        self.files = files
        self.calls: list[str] = []

    def get(self, url, timeout=None, **kw):
        self.calls.append(url)
        if url not in self.files:
            return FakeResp(status=404)
        return FakeResp(self.files[url])


def team(abbr="AAA", logo=True, dark=True):
    return Team(
        abbr=abbr,
        logo_url=f"http://x/{abbr}.png" if logo else None,
        logo_dark_url=f"http://x/{abbr}-dark.png" if dark else None,
    )


def make_store(tmp_path, files, **kw):
    sess = FakeSession(files)
    store = LogoStore(tmp_path / "cache", kw.pop("sizes", (16, 24)), session=sess, **kw)
    return store, sess


# ---- process_logo ---------------------------------------------------------------


def test_trims_transparent_border_and_fits_box():
    src = solid(40, 20, (255, 0, 0), margin=30)  # 100x80 canvas, 40x20 content
    rgb, mask = process_logo(src, 20)
    assert rgb.size == mask.size == (20, 10)  # cropped, wide logo -> 20x10


def test_preserves_aspect_ratio_tall_and_small_sizes():
    rgb, _ = process_logo(solid(10, 40, (0, 255, 0)), 16)
    assert rgb.size == (4, 16)
    rgb, _ = process_logo(solid(30, 30, (0, 255, 0)), 10)
    assert rgb.size == (10, 10)


def test_transparent_becomes_black_and_mask_marks_lit():
    src = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    src.paste(Image.new("RGBA", (20, 40), (255, 255, 255, 255)), (0, 0))
    # transparent pixels that carry a bright color must not leak into the result
    src.paste(Image.new("RGBA", (20, 40), (255, 0, 255, 0)), (20, 0))
    rgb, mask = process_logo(src, 20)
    assert rgb.size == (10, 20)  # trimmed to the opaque half only
    assert rgb.mode == "RGB" and mask.mode == "L"

    ring = Image.new("RGBA", (60, 60), (0, 0, 0, 0))
    ring.paste(Image.new("RGBA", (20, 20), (255, 255, 255, 255)), (0, 0))
    ring.paste(Image.new("RGBA", (20, 20), (255, 255, 255, 255)), (40, 40))
    rgb, mask = process_logo(ring, 12)
    assert rgb.getpixel((6, 0)) == (0, 0, 0)  # gap between the two squares is black
    assert mask.getpixel((6, 0)) == 0
    assert mask.getpixel((0, 0)) == 255
    assert rgb.getpixel((0, 0)) == (255, 255, 255)


def test_no_dark_fringe_on_edges():
    # white disc-ish blob: edge pixels must stay white-ish, not gray/colored, wherever lit
    src = Image.new("RGBA", (64, 64), (255, 255, 255, 0))
    src.paste(Image.new("RGBA", (40, 40), (255, 255, 255, 255)), (10, 10))
    rgb, mask = process_logo(src, 10, lift=False)
    for p, a in zip(logos._pixels(rgb), logos._pixels(mask), strict=True):
        if a == 255:
            assert min(p) >= 235


def test_fully_transparent_source_is_safe():
    rgb, mask = process_logo(Image.new("RGBA", (30, 30), (0, 0, 0, 0)), 16)
    assert rgb.size == mask.size == (1, 1)
    assert mask.getpixel((0, 0)) == 0


def test_dark_logo_is_lifted_but_not_when_disabled():
    src = solid(30, 30, (0, 20, 50))
    lifted, mask = process_logo(src, 16)
    plain, _ = process_logo(src, 16, lift=False)
    lum = lambda im: sum(logos._pixels(im.convert("L")))  # noqa: E731
    assert lum(lifted) > lum(plain) * 1.5
    assert max(lifted.getpixel((8, 8))) < 200  # lifted, not washed out to white


# ---- readability ----------------------------------------------------------------


def test_readability_prefers_bright_over_near_black():
    bright = process_logo(solid(30, 30, (240, 200, 40)), 20, lift=False)
    dark = process_logo(solid(30, 30, (5, 5, 20)), 20, lift=False)
    assert readability(*bright) > readability(*dark) * 5
    assert readability(Image.new("RGB", (4, 4)), Image.new("L", (4, 4))) == 0.0


# ---- store ----------------------------------------------------------------------


def test_prepare_sync_writes_cache_layout_and_get_returns_image(tmp_path):
    t = team()
    store, sess = make_store(
        tmp_path,
        {
            t.logo_url: png(solid(40, 20, (255, 0, 0), margin=5)),
            t.logo_dark_url: png(solid(40, 20, (255, 255, 0), margin=5)),
        },
    )
    assert store.get("nfl", "AAA", 16) is None  # nothing prepared yet
    assert store.prepare_sync("nfl", t) is True
    root = tmp_path / "cache" / "nfl"
    assert (root / "AAA.png").exists() and (root / "AAA.dark.png").exists()
    assert (root / "AAA" / "logo_16.png").exists() and (root / "AAA" / "dark_24.png").exists()
    assert (root / "index.json").exists()
    img = store.get("nfl", "aaa", 16)  # case-insensitive abbr
    assert img is not None and img.mode == "RGB" and img.size == (16, 8)
    mask = store.get_mask("nfl", "AAA", 16)
    assert mask is not None and mask.mode == "L" and mask.size == img.size
    assert store.chosen_variant("nfl", "AAA") == "dark"  # yellow beats red


def test_auto_picks_brighter_variant(tmp_path):
    t = team()
    store, _ = make_store(
        tmp_path,
        {
            t.logo_url: png(solid(30, 30, (0, 0, 25))),  # navy on transparent
            t.logo_dark_url: png(solid(30, 30, (230, 230, 230))),
        },
    )
    assert store.prepare_sync("nba", t)
    assert store.chosen_variant("nba", "AAA") == "dark"

    t2 = team("BBB")
    store2, _ = make_store(
        tmp_path / "other",
        {
            t2.logo_url: png(solid(30, 30, (230, 230, 230))),
            t2.logo_dark_url: png(solid(30, 30, (0, 0, 25))),
        },
    )
    assert store2.prepare_sync("nba", t2)
    assert store2.chosen_variant("nba", "BBB") == "logo"
    assert store2.get("nba", "BBB", 16).getpixel((8, 8))[0] > 150


def test_single_variant_used_when_other_missing(tmp_path):
    t = team(dark=False)
    store, _ = make_store(tmp_path, {t.logo_url: png(solid(30, 30, (200, 0, 0)))})
    assert store.prepare_sync("nfl", t)
    assert store.chosen_variant("nfl", "AAA") == "logo"
    assert store.get("nfl", "AAA", 24) is not None

    # one URL 404s, the other works: still usable
    t2 = team("BBB")
    store2, _ = make_store(tmp_path / "b", {t2.logo_dark_url: png(solid(30, 30, (200, 0, 0)))})
    assert store2.prepare_sync("nfl", t2)
    assert store2.chosen_variant("nfl", "BBB") == "dark"


def test_forced_variant_config(tmp_path):
    t = team()
    files = {
        t.logo_url: png(solid(30, 30, (0, 0, 25))),
        t.logo_dark_url: png(solid(30, 30, (230, 230, 230))),
    }
    store, _ = make_store(tmp_path, files, variant="logo")
    assert store.prepare_sync("nfl", t)
    assert store.chosen_variant("nfl", "AAA") == "dark"  # auto choice is still recorded
    assert store.get("nfl", "AAA", 16).getpixel((8, 8))[0] < 80  # but "logo" (navy) is served
    assert store.get_variant("nfl", "AAA", 16, "dark")[0].getpixel((8, 8))[0] > 150


def test_cache_reuse_within_max_age_no_second_download(tmp_path):
    t = team()
    store, sess = make_store(
        tmp_path,
        {
            t.logo_url: png(solid(30, 30, (200, 0, 0))),
            t.logo_dark_url: png(solid(30, 30, (9, 9, 9))),
        },
    )
    assert store.prepare_sync("nfl", t)
    assert len(sess.calls) == 2

    # a brand-new store (fresh process) over the same cache must not re-download
    store2 = LogoStore(tmp_path / "cache", (16, 24), session=sess)
    assert store2.prepare_sync("nfl", t)
    assert len(sess.calls) == 2
    assert store2.get("nfl", "AAA", 16) is not None


def test_missing_scaled_copy_is_rebuilt_without_download(tmp_path):
    t = team()
    store, sess = make_store(
        tmp_path,
        {
            t.logo_url: png(solid(30, 30, (200, 0, 0))),
            t.logo_dark_url: png(solid(30, 30, (9, 9, 9))),
        },
    )
    assert store.prepare_sync("nfl", t)
    scaled = tmp_path / "cache" / "nfl" / "AAA" / "logo_16.png"
    scaled.unlink()
    store2 = LogoStore(tmp_path / "cache", (16, 24), session=sess)
    assert store2.prepare_sync("nfl", t)
    assert scaled.exists() and len(sess.calls) == 2


def test_refresh_after_expiry(tmp_path):
    t = team()
    store, sess = make_store(
        tmp_path,
        {
            t.logo_url: png(solid(30, 30, (200, 0, 0))),
            t.logo_dark_url: png(solid(30, 30, (9, 9, 9))),
        },
        max_age_days=30,
    )
    assert store.prepare_sync("nfl", t)
    assert len(sess.calls) == 2
    old = time.time() - 31 * 86400
    for name in ("AAA.png", "AAA.dark.png"):
        os.utime(tmp_path / "cache" / "nfl" / name, (old, old))
    store2 = LogoStore(tmp_path / "cache", (16, 24), session=sess, max_age_days=30)
    assert store2.prepare_sync("nfl", t)
    assert len(sess.calls) == 4


def test_failure_returns_none_never_raises_and_warns_once(tmp_path, caplog):
    t = team()
    store, sess = make_store(tmp_path, {})  # everything 404s
    caplog.set_level("DEBUG", logger="sportsticker.logos")
    store.request("nfl", t)
    assert store.wait_idle(5)
    assert store.get("nfl", "AAA", 16) is None
    assert store.get_mask("nfl", "AAA", 16) is None
    assert store.chosen_variant("nfl", "AAA") is None
    n = len(sess.calls)
    store.request("nfl", t)  # inside the 1 hour back-off: ignored
    assert store.wait_idle(5)
    assert len(sess.calls) == n
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1

    # past the back-off the team is retried; still no extra warning
    real = time.time
    store._clock = lambda: real() + 3601
    store.request("nfl", t)
    assert store.wait_idle(5)
    assert len(sess.calls) > n
    assert len([r for r in caplog.records if r.levelname == "WARNING"]) == 1


def test_failure_then_success_after_retry_window(tmp_path):
    t = team(dark=False)
    store, sess = make_store(tmp_path, {})
    store.request("nfl", t)
    assert store.wait_idle(5)
    assert store.get("nfl", "AAA", 16) is None
    sess.files[t.logo_url] = png(solid(30, 30, (200, 0, 0)))
    real = time.time
    store._clock = lambda: real() + 3601
    store.request("nfl", t)
    assert store.wait_idle(5)
    assert store.get("nfl", "AAA", 16) is not None


def test_garbage_download_is_a_failure_not_an_exception(tmp_path):
    t = team(dark=False)
    store, _ = make_store(tmp_path, {t.logo_url: b"<html>not an image</html>"})
    assert store.prepare_sync("nfl", t) is False
    assert store.get("nfl", "AAA", 16) is None


def test_request_background_worker_and_dedupe(tmp_path):
    t = team()
    store, sess = make_store(
        tmp_path,
        {
            t.logo_url: png(solid(30, 30, (200, 0, 0))),
            t.logo_dark_url: png(solid(30, 30, (250, 250, 250))),
        },
    )
    for _ in range(5):
        store.request("nfl", t)
    assert store.wait_idle(10)
    store.request("nfl", t)  # already done: no-op
    assert store.wait_idle(10)
    assert len(sess.calls) == 2
    assert store.get("nfl", "AAA", 24) is not None
    store.close()


def test_get_never_touches_network(tmp_path):
    t = team()
    store, sess = make_store(
        tmp_path,
        {
            t.logo_url: png(solid(30, 30, (200, 0, 0))),
            t.logo_dark_url: png(solid(30, 30, (9, 9, 9))),
        },
    )
    for _ in range(3):
        assert store.get("nfl", "AAA", 16) is None  # unknown team, no network
    assert store.get("nfl", "ZZZ", 99) is None
    assert sess.calls == []

    store.prepare_sync("nfl", t)
    calls = len(sess.calls)

    class Boom:
        def get(self, *a, **k):
            raise AssertionError("network used by get()")

    store._session = Boom()
    fresh = LogoStore(tmp_path / "cache", (16, 24), session=Boom())
    assert fresh.get("nfl", "AAA", 16) is not None  # lazy disk load only
    assert fresh.get("nfl", "AAA", 16) is fresh.get("nfl", "AAA", 16)
    assert fresh.get("nfl", "AAA", 17) is None  # size not prepared: None, no resize
    assert store.get("nfl", "AAA", 24) is not None
    assert len(sess.calls) == calls


def test_nothing_written_outside_cache_dir(tmp_path):
    t = team()
    store, _ = make_store(
        tmp_path / "work",
        {
            t.logo_url: png(solid(30, 30, (200, 0, 0))),
            t.logo_dark_url: png(solid(30, 30, (9, 9, 9))),
        },
    )
    store.prepare_sync("nfl", t)
    files = [p for p in (tmp_path / "work").rglob("*") if p.is_file()]
    assert files and all((tmp_path / "work" / "cache") in p.parents for p in files)


def test_bad_variant_rejected(tmp_path):
    with pytest.raises(ValueError):
        LogoStore(tmp_path, (16,), variant="neon")


# ---- prefetch ---------------------------------------------------------------------


class JsonResp:
    def __init__(self, data):
        self._d = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._d


class EspnSession:
    def __init__(self, payloads):
        self.payloads = payloads
        self.urls = []

    def get(self, url, params=None, timeout=None):
        self.urls.append((url, params))
        for frag, data in self.payloads.items():
            if frag in url:
                return JsonResp(data)
        raise AssertionError(url)


def _espn_team(abbr, extra_logos=()):
    logos_ = [
        {"href": f"http://x/{abbr}-scoreboard.png", "rel": ["scoreboard", "default"]},
        {"href": f"http://x/{abbr}.png", "rel": ["full", "default"]},
        {"href": f"http://x/{abbr}-dark.png", "rel": ["full", "dark"]},
        *extra_logos,
    ]
    return {
        "abbreviation": abbr,
        "shortDisplayName": abbr.title(),
        "color": "ff0000",
        "logos": logos_,
    }


def test_team_from_espn_prefers_full_over_scoreboard():
    t = team_from_espn(_espn_team("KC"))
    assert t.logo_url == "http://x/KC.png" and t.logo_dark_url == "http://x/KC-dark.png"
    only_sb = {
        "abbreviation": "ZZ",
        "logos": [{"href": "http://x/zz-sb.png", "rel": ["scoreboard", "default"]}],
    }
    assert team_from_espn(only_sb).logo_url == "http://x/zz-sb.png"
    assert team_from_espn({"abbreviation": "NO", "logos": []}) is None


def test_prefetch_counts_ok_and_failed(tmp_path):
    payload = {
        "sports": [
            {"leagues": [{"teams": [{"team": _espn_team("AA")}, {"team": _espn_team("BB")}]}]}
        ]
    }
    files = {
        "http://x/AA.png": png(solid(30, 30, (200, 0, 0))),
        "http://x/AA-dark.png": png(solid(30, 30, (250, 250, 250))),
    }  # BB has nothing downloadable
    store = LogoStore(tmp_path / "c", (16,), session=FakeSession(files))
    result = prefetch(["nfl", "bogus"], store, session=EspnSession({"/nfl/teams": payload}), pace=0)
    assert result["nfl"] == 1 and result["nfl_failed"] == 1
    assert result["bogus"] == 0 and result["bogus_failed"] == 1
    assert store.get("nfl", "AA", 16) is not None


def test_prefetch_college_uses_standings_group(tmp_path):
    standings = {
        "children": [{"standings": {"entries": [{"team": {**_espn_team("FBS1"), "id": "1"}}]}}]
    }
    sess = EspnSession({"/college-football/standings": standings})
    teams = logos.fetch_teams("ncaaf", session=sess)
    assert [t.abbr for t in teams] == ["FBS1"]
    assert sess.urls[0][1]["group"] == 80
