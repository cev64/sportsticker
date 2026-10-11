"""Team logos for the LED panel: download, pre-scale, cache, look up fast.

Design rules:
- get() is called from the render loop: it only does a dict lookup (plus, at
  most once per team/size, a tiny PNG read from the local cache). It never
  touches the network and never resizes.
- All slow work (download, trim, resize, scoring) happens on one background
  daemon thread (request) or synchronously on the caller's thread
  (prepare_sync, used by the prefetch command and the snapshot tools).
- Logos are team trademarks. They are only ever written below `cache_dir`
  (default ~/.cache/sportsticker/logos), never inside the repository.

Cache layout, per league:
    {cache_dir}/{league}/{ABBR}.png            original, default variant
    {cache_dir}/{league}/{ABBR}.dark.png       original, "dark" variant
    {cache_dir}/{league}/{ABBR}/{variant}_{size}.png
                                               pre-scaled RGBA: RGB is the
                                               image composited on black, A is
                                               the "this pixel is lit" mask
    {cache_dir}/{league}/index.json            fetch metadata + chosen variant
"""

from __future__ import annotations

import io
import json
import logging
import os
import queue
import re
import statistics
import threading
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import requests
from PIL import Image

from .models import LEAGUES, Team

log = logging.getLogger(__name__)

VARIANTS = ("logo", "dark")  # "logo" = ESPN's default art, "dark" = for dark backgrounds
RETRY_AFTER_FAILURE_S = 3600.0
SCORE_SIZE = 20  # variants are compared at this bounding box
PIPELINE_VERSION = 6  # bump when process_logo changes: invalidates cached scaled copies

# ---- image processing tunables -------------------------------------------------

TRIM_ALPHA = 16  # pixels at or below this alpha count as empty when trimming borders
LIT_ALPHA = 128  # mask value at or above which an LED counts as lit
CONTRAST = 1.15
SATURATION = 1.25
# Alpha below this (after resizing) is snapped to fully transparent: a faint
# 10% edge pixel on an LED panel is just a dim speck of color mush.
SNAP_ALPHA_SMALL = 60  # sizes <= 24
SNAP_ALPHA_LARGE = 36
# Dark logos (navy, black) vanish on black. Luminance below LIFT_KNEE is pulled
# up, strength scaled by how dark the whole logo is.
ALPHA_GAMMA = 0.7
PEAK_TARGET = 235
MAX_PEAK_GAIN = 1.6
LIFT_KNEE = 0.30
LIFT_MAX_GAIN = 3.0  # beyond this the rest is filled with gray, not saturated color
LIFT_AMOUNT = 0.65


def _pixels(img: Image.Image) -> list:
    """Flat pixel list (getdata is deprecated in newer Pillow)."""
    fn = getattr(img, "get_flattened_data", None) or img.getdata
    return list(fn())


def _lum(r: float, g: float, b: float) -> float:
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def _trim(img: Image.Image) -> Image.Image | None:
    alpha = img.getchannel("A").point(lambda v: 255 if v > TRIM_ALPHA else 0)
    box = alpha.getbbox()
    return img.crop(box) if box else None


def process_logo(src: Image.Image, size: int, lift: bool = True) -> tuple[Image.Image, Image.Image]:
    """Turn an original logo into an LED-ready (RGB-on-black, L mask) pair.

    The result fits inside a size x size box, keeps aspect ratio and is cropped
    to its content, so a wide logo at size 20 may be 20x13. Steps: trim empty
    border, premultiplied-alpha LANCZOS resize (no dark fringes), snap faint
    alpha to 0, contrast + saturation boost, optional dark lift, composite
    onto black. With lift=False the dark lift is skipped (used for scoring).
    """
    size = max(1, int(size))
    rgba = _trim(src.convert("RGBA"))
    if rgba is None:  # fully transparent source: nothing to light up
        return Image.new("RGB", (1, 1)), Image.new("L", (1, 1))

    w, h = rgba.size
    k = size / max(w, h)
    nw, nh = max(1, min(size, round(w * k))), max(1, min(size, round(h * k)))
    # Resize in premultiplied space so transparent pixels' (arbitrary) colors
    # do not bleed into the edges, then go back to straight alpha.
    small = rgba.convert("RGBa").resize((nw, nh), Image.LANCZOS).convert("RGBA")

    snap = SNAP_ALPHA_SMALL if size <= 24 else SNAP_ALPHA_LARGE
    ramp = 255.0 / (255 - snap)
    # Thin strokes (spurs, outlines) only reach partial alpha after downscaling
    # and would glow dimly; a gamma below 1 on alpha keeps them visible.
    alpha = small.getchannel("A").point(
        lambda a: (
            0
            if a < snap
            else min(255, round(255 * (((a - snap) * ramp * 0.5 + a * 0.5) / 255) ** ALPHA_GAMMA))
        )
    )
    rgb = _boost(small.convert("RGB"), alpha)
    lifted = False
    if lift:
        rgb, lifted = _lift_dark(rgb, alpha)

    out = Image.composite(rgb, Image.new("RGB", rgb.size), alpha)
    if lift and not lifted:  # dark logos already got their (gentler) lift
        out = _normalize_peak(out, alpha)
    return out, alpha


def _normalize_peak(img: Image.Image, alpha: Image.Image) -> Image.Image:
    """Thin or gray logos never reach full brightness; raise them toward it (<= 1.6x)."""
    peak = max(
        (max(p) for p, a in zip(_pixels(img), _pixels(alpha), strict=True) if a >= LIT_ALPHA),
        default=255,
    )
    if peak >= PEAK_TARGET or peak == 0:
        return img
    gain = min(MAX_PEAK_GAIN, PEAK_TARGET / peak)
    return img.point(lambda v: min(255, round(v * gain)))


def _boost(rgb: Image.Image, alpha: Image.Image) -> Image.Image:
    """Contrast about the mean of the *lit* pixels (not the black background)."""
    from PIL import ImageEnhance

    px, al = list(_pixels(rgb)), list(_pixels(alpha))
    wsum = sum(al)
    if wsum == 0:
        return rgb
    mean = sum(_lum(*p) * 255 * a for p, a in zip(px, al, strict=True)) / wsum
    flat = Image.new("RGB", rgb.size, (round(mean),) * 3)
    out = Image.blend(flat, rgb, CONTRAST)
    return ImageEnhance.Color(out).enhance(SATURATION)


def _lift_dark(rgb: Image.Image, alpha: Image.Image) -> tuple[Image.Image, bool]:
    px, al = list(_pixels(rgb)), list(_pixels(alpha))
    lums = sorted(_lum(*p) for p, a in zip(px, al, strict=True) if a >= LIT_ALPHA)
    if not lums:
        return rgb, False
    p75 = lums[min(len(lums) - 1, int(len(lums) * 0.75))]
    strength = max(0.0, min(1.0, (0.45 - p75) / 0.20)) * LIFT_AMOUNT
    if strength <= 0:
        return rgb, False
    out = []
    for r, g, b in px:
        lum = _lum(r, g, b)
        if lum >= LIFT_KNEE:
            out.append((r, g, b))
            continue
        target = lum + (LIFT_KNEE - lum) * strength
        m = max(r, g, b)
        if lum > 0.004 and m > 0:
            gain = min(target / lum, 255.0 / m, LIFT_MAX_GAIN)
            r, g, b = r * gain, g * gain, b * gain
        add = max(0.0, (target - _lum(r, g, b)) * 255)  # whatever the gain could not reach
        out.append(tuple(min(255, round(v + add)) for v in (r, g, b)))
    img = Image.new("RGB", rgb.size)
    img.putdata(out)
    return img, True


def readability(img: Image.Image, mask: Image.Image) -> float:
    """Score 0..1 (higher is better) for how well a logo reads on black at LED size.

    Coverage of lit pixels in the bounding box x their mean perceived
    brightness, discounted for the share of near-black pixels and boosted a
    little for tonal contrast between parts of the logo.
    """
    rgb = img.convert("RGB")
    px = list(_pixels(rgb))
    lit = [_lum(*p) for p, a in zip(px, _pixels(mask.convert("L")), strict=True) if a >= LIT_ALPHA]
    if not lit:
        return 0.0
    coverage = len(lit) / max(1, len(px))
    mean = sum(lit) / len(lit)
    dark_frac = sum(1 for v in lit if v < 0.14) / len(lit)
    spread = statistics.pstdev(lit) if len(lit) > 1 else 0.0
    return coverage * mean * (1.0 - 0.85 * dark_frac) * (1.0 + min(spread, 0.3))


# ---- store -----------------------------------------------------------------------

_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def _safe(name: str) -> str:
    return _SAFE.sub("_", name) or "_"


class LogoStore:
    """Background-loaded, pre-scaled team logos. See module docstring."""

    def __init__(
        self,
        cache_dir: Path,
        sizes: Iterable[int],
        max_age_days: float = 30,
        variant: str = "auto",
        session=None,
        timeout: float = 10,
    ) -> None:
        if variant not in ("auto", *VARIANTS):
            raise ValueError(f"variant must be auto, logo or dark, got {variant!r}")
        self.cache_dir = Path(cache_dir).expanduser()
        self.sizes = tuple(sorted({int(s) for s in sizes}))
        self.max_age_days = max_age_days
        self.variant = variant
        self.timeout = timeout
        self._session = session
        self._clock = time.time  # tests may replace

        self._lock = threading.RLock()
        self._idle = threading.Condition(self._lock)
        self._images: dict[tuple[str, str, str, int], tuple[Image.Image, Image.Image]] = {}
        self._disk_miss: set[tuple[str, str, str, int]] = set()
        self._indexes: dict[str, dict] = {}
        self._chosen: dict[tuple[str, str], str] = {}
        self._pending: set[tuple[str, str]] = set()
        self._done: dict[tuple[str, str], float] = {}
        self._retry_at: dict[tuple[str, str], float] = {}
        self._warned: set[tuple[str, str]] = set()
        self._queue: queue.Queue[tuple[str, Team] | None] = queue.Queue()
        self._thread: threading.Thread | None = None

    # ---- public API ----------------------------------------------------------

    def request(self, league: str, team: Team) -> None:
        """Queue a team for background preparation. Cheap, never blocks, never raises."""
        try:
            key = (league, team.abbr.upper())
            now = self._clock()
            with self._lock:
                if key in self._pending:
                    return
                done = self._done.get(key)
                if done is not None and now - done < self.max_age_days * 86400:
                    return
                if now < self._retry_at.get(key, 0.0):
                    return
                self._pending.add(key)
                self._start_worker()
            self._queue.put((league, team))
        except Exception:  # pragma: no cover - defensive: callers must never see errors
            log.exception("logo request failed for %s", team)

    def get(self, league: str, abbr: str, size: int) -> Image.Image | None:
        """Prepared RGB logo for the configured variant, or None if not ready.

        Fast path: a dict lookup. The returned image is shared: do not modify it.
        """
        entry = self._lookup(league, abbr, size, None)
        return entry[0] if entry else None

    def get_mask(self, league: str, abbr: str, size: int) -> Image.Image | None:
        """'L' mask of the same logo: 255 where an LED is lit, 0 elsewhere."""
        entry = self._lookup(league, abbr, size, None)
        return entry[1] if entry else None

    def get_variant(
        self, league: str, abbr: str, size: int, variant: str
    ) -> tuple[Image.Image, Image.Image] | None:
        """(rgb, mask) of one specific variant ("logo" or "dark"), for previews."""
        return self._lookup(league, abbr, size, variant)

    def chosen_variant(self, league: str, abbr: str) -> str | None:
        key = (league, abbr.upper())
        with self._lock:
            if key in self._chosen:
                return self._chosen[key]
            entry = self._index(league).get(key[1])
            chosen = entry.get("chosen") if isinstance(entry, dict) else None
            if chosen in VARIANTS:
                self._chosen[key] = chosen
                return chosen
        return None

    def prepare_sync(self, league: str, team: Team) -> bool:
        """Do the worker's job on the calling thread. True if the team is ready."""
        key = (league, team.abbr.upper())
        try:
            self._prepare(league, team)
        except Exception as e:
            self._record_failure(key, e)
            return False
        return True

    def wait_idle(self, timeout: float | None = None) -> bool:
        """Block until the background queue is drained (for tests and tools)."""
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._idle:
            while self._pending:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                self._idle.wait(remaining)
        return True

    def close(self) -> None:
        """Stop the worker thread (optional: it is a daemon)."""
        with self._lock:
            thread = self._thread
            self._thread = None
        if thread is not None:
            self._queue.put(None)

    # ---- lookup ------------------------------------------------------------

    def _effective_variant(self, league: str, abbr: str, override: str | None) -> str | None:
        if override in VARIANTS:
            return override
        if self.variant in VARIANTS:
            return self.variant
        return self.chosen_variant(league, abbr)

    def _lookup(self, league, abbr, size, override):
        abbr = abbr.upper()
        variant = self._effective_variant(league, abbr, override)
        if variant is None:
            return None
        key = (league, abbr, variant, int(size))
        entry = self._images.get(key)
        if entry is not None:
            return entry
        if key in self._disk_miss:
            return None
        entry = self._load_scaled(key)  # tiny local file, once per key
        if entry is None and override is None and self.variant in VARIANTS:
            # configured variant missing for this team: fall back to what exists
            other = "dark" if variant == "logo" else "logo"
            if self.chosen_variant(league, abbr) == other:
                return self._lookup(league, abbr, size, other)
        return entry

    def _scaled_path(self, league: str, abbr: str, variant: str, size: int) -> Path:
        return self.cache_dir / _safe(league) / _safe(abbr) / f"{variant}_{size}.png"

    def _load_scaled(self, key):
        league, abbr, variant, size = key
        path = self._scaled_path(league, abbr, variant, size)
        try:
            with Image.open(path) as im:
                im.load()
                rgba = im.convert("RGBA")
        except (OSError, ValueError):
            with self._lock:
                self._disk_miss.add(key)
            return None
        entry = (rgba.convert("RGB"), rgba.getchannel("A"))
        with self._lock:
            self._images[key] = entry
            self._disk_miss.discard(key)
        return entry

    # ---- worker ----------------------------------------------------------------

    def _start_worker(self) -> None:
        # caller holds self._lock
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, name="logo-worker", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        while True:
            job = self._queue.get()
            if job is None:
                return
            league, team = job
            key = (league, team.abbr.upper())
            try:
                self._prepare(league, team)
            except Exception as e:
                self._record_failure(key, e)
            finally:
                with self._idle:
                    self._pending.discard(key)
                    self._idle.notify_all()

    def _record_failure(self, key: tuple[str, str], err: Exception) -> None:
        with self._lock:
            self._retry_at[key] = self._clock() + RETRY_AFTER_FAILURE_S
            first = key not in self._warned
            self._warned.add(key)
        if first:
            log.warning("logo for %s/%s unavailable: %s", key[0], key[1], err)
        else:
            log.debug("logo for %s/%s still unavailable: %s", key[0], key[1], err)

    # ---- preparation (shared by worker and prepare_sync) -------------------------

    def _http(self):
        if self._session is None:
            s = requests.Session()
            s.headers["User-Agent"] = "sportsticker/0.1 (LED scoreboard)"
            self._session = s
        return self._session

    def _download(self, url: str) -> Image.Image:
        resp = self._http().get(url, timeout=self.timeout)
        resp.raise_for_status()
        with Image.open(io.BytesIO(resp.content)) as im:
            im.load()
            return im.convert("RGBA")

    @staticmethod
    def _write_atomic(path: Path, write) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            write(tmp)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)

    def _original_path(self, league: str, abbr: str, variant: str) -> Path:
        name = f"{_safe(abbr)}.png" if variant == "logo" else f"{_safe(abbr)}.dark.png"
        return self.cache_dir / _safe(league) / name

    def _fetch_original(
        self, path: Path, url: str | None, known_url: str | None
    ) -> tuple[Image.Image | None, bool]:
        """Return (original image or None, freshly_downloaded)."""
        exists = path.exists()
        fresh = False
        if exists and url is not None and url == known_url:
            fresh = self._clock() - path.stat().st_mtime < self.max_age_days * 86400
        elif exists and url is None:
            fresh = True  # nothing to refresh from; keep what we have
        if fresh:
            try:
                with Image.open(path) as im:
                    im.load()
                    return im.convert("RGBA"), False
            except (OSError, ValueError):
                pass  # corrupt cache file: fall through and download again
        if url is None:
            return None, False
        try:
            img = self._download(url)
        except Exception as e:
            if exists:  # stale but usable beats nothing
                log.debug("refresh of %s failed (%s); using stale copy", path.name, e)
                try:
                    with Image.open(path) as im:
                        im.load()
                        return im.convert("RGBA"), False
                except (OSError, ValueError):
                    pass
            log.debug("download of %s failed: %s", url, e)
            return None, False
        self._write_atomic(path, lambda p: img.save(p, "PNG"))
        return img, True

    def _prepare(self, league: str, team: Team) -> None:
        abbr = team.abbr.upper()
        key = (league, abbr)
        urls = {"logo": team.logo_url, "dark": team.logo_dark_url}
        with self._lock:
            entry = dict(self._index(league).get(abbr) or {})
        known = entry.get("urls") or {}

        originals: dict[str, Image.Image] = {}
        downloaded = False
        errors = []
        for variant in VARIANTS:
            path = self._original_path(league, abbr, variant)
            img, new = self._fetch_original(path, urls[variant], known.get(variant))
            if img is None:
                if urls[variant]:
                    errors.append(f"{variant}: download failed ({urls[variant]})")
                continue
            originals[variant] = img
            downloaded = downloaded or new
        if not originals:
            raise RuntimeError("; ".join(errors) or "team has no logo URLs")

        stale = entry.get("pipeline") != PIPELINE_VERSION
        chosen = entry.get("chosen")
        scores = entry.get("scores") or {}
        if downloaded or stale or chosen not in originals or not scores:
            scores = {}
            for variant, img in originals.items():
                small, mask = process_logo(img, SCORE_SIZE, lift=False)
                scores[variant] = round(readability(small, mask), 4)
            chosen = self._choose(scores)

        for variant, img in originals.items():
            for size in self.sizes:
                path = self._scaled_path(league, abbr, variant, size)
                orig_path = self._original_path(league, abbr, variant)
                if not downloaded and not stale and self._is_current(path, orig_path):
                    continue
                small, mask = process_logo(img, size)
                rgba = small.convert("RGBA")
                rgba.putalpha(mask)
                self._write_atomic(path, lambda p, im=rgba: im.save(p, "PNG"))
                with self._lock:
                    self._images.pop((league, abbr, variant, size), None)
                    self._disk_miss.discard((league, abbr, variant, size))

        new_entry = {
            "urls": {v: urls[v] or known.get(v) for v in VARIANTS},
            "fetched_at": (
                datetime.now(UTC).isoformat(timespec="seconds")
                if downloaded or "fetched_at" not in entry
                else entry["fetched_at"]
            ),
            "chosen": chosen,
            "scores": scores,
            "available": sorted(originals),
            "pipeline": PIPELINE_VERSION,
        }
        with self._lock:
            self._index(league)[abbr] = new_entry
            self._chosen[key] = chosen
            self._write_index(league)

        # warm memory with the configured variant so get() is a dict lookup
        variant = self.variant if self.variant in originals else chosen
        for size in self.sizes:
            self._load_scaled((league, abbr, variant, size))
        with self._lock:
            self._done[key] = self._clock()
            self._retry_at.pop(key, None)
            self._warned.discard(key)

    @staticmethod
    def _choose(scores: dict[str, float]) -> str:
        if len(scores) == 1:
            return next(iter(scores))
        # ESPN draws "dark" for dark backgrounds, so it wins near-ties.
        return "dark" if scores["dark"] >= scores["logo"] * 0.97 else "logo"

    @staticmethod
    def _is_current(scaled: Path, original: Path) -> bool:
        try:
            return scaled.stat().st_mtime >= original.stat().st_mtime
        except OSError:
            return False

    # ---- index.json ----------------------------------------------------------------

    def _index_path(self, league: str) -> Path:
        return self.cache_dir / _safe(league) / "index.json"

    def _index(self, league: str) -> dict:
        # caller may hold self._lock; RLock makes that fine
        with self._lock:
            idx = self._indexes.get(league)
            if idx is None:
                try:
                    idx = json.loads(self._index_path(league).read_text())
                    if not isinstance(idx, dict):
                        idx = {}
                except (OSError, ValueError):
                    idx = {}
                self._indexes[league] = idx
            return idx

    def _write_index(self, league: str) -> None:
        data = json.dumps(self._index(league), indent=1, sort_keys=True)
        try:
            self._write_atomic(self._index_path(league), lambda p: p.write_text(data))
        except OSError as e:
            log.warning("could not write logo index for %s: %s", league, e)


# ---- prefetch -------------------------------------------------------------------

ESPN_SITE = "https://site.api.espn.com/apis/site/v2/sports"
ESPN_STANDINGS = "https://site.api.espn.com/apis/v2/sports"
# The teams endpoint ignores `groups`, so the college subsets come from the
# standings endpoint, which does honor `group` (80 = FBS, 50 = Division I).
COLLEGE_GROUPS = {"ncaaf": 80, "ncaab": 50}


def _pick_logo(logos: list[dict], want: str) -> str | None:
    """Best href for 'default' or 'dark' among a team's logos[]."""

    def rels(x):
        return [str(r) for r in x.get("rel", [])]

    ranked = []
    for item in logos:
        href = item.get("href")
        r = rels(item)
        if not href or want not in r:
            continue
        score = (("full" in r) * 2) - (("scoreboard" in r) * 3)
        ranked.append((score, href))
    if not ranked:
        return None
    return max(ranked, key=lambda t: t[0])[1]


def team_from_espn(raw: dict) -> Team | None:
    """Build a Team from an ESPN team object (teams or standings payload)."""
    abbr = raw.get("abbreviation")
    if not abbr:
        return None
    logos = raw.get("logos") or []
    default = _pick_logo(logos, "default")
    dark = _pick_logo(logos, "dark")
    if default is None and dark is None:
        return None
    return Team(
        abbr=abbr,
        name=raw.get("shortDisplayName") or raw.get("name") or "",
        color=raw.get("color"),
        alt_color=raw.get("alternateColor"),
        logo_url=default,
        logo_dark_url=dark,
        id=str(raw.get("id", "")),
    )


def _walk_standings(node: dict, out: list[dict]) -> None:
    for child in node.get("children", []):
        _walk_standings(child, out)
    for entry in (node.get("standings") or {}).get("entries", []):
        if isinstance(entry.get("team"), dict):
            out.append(entry["team"])


def fetch_teams(league_key: str, session=None, timeout: float = 20) -> list[Team]:
    """Every team ESPN lists for a league (FBS / D1 only for college)."""
    sess = session or requests.Session()
    lg = LEAGUES[league_key]
    raw: list[dict] = []
    group = COLLEGE_GROUPS.get(league_key)
    if group is not None:
        try:
            r = sess.get(
                f"{ESPN_STANDINGS}/{lg.path}/standings",
                params={"group": group, "level": 3},
                timeout=timeout,
            )
            r.raise_for_status()
            _walk_standings(r.json(), raw)
        except Exception as e:
            log.warning("%s standings lookup failed (%s); using full teams list", league_key, e)
    if not raw:
        r = sess.get(f"{ESPN_SITE}/{lg.path}/teams", params={"limit": 1000}, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        for sport in data.get("sports", []):
            for league in sport.get("leagues", []):
                raw.extend(t["team"] for t in league.get("teams", []) if "team" in t)
    teams, seen = [], set()
    for item in raw:
        team = team_from_espn(item)
        if team and team.abbr.upper() not in seen:
            seen.add(team.abbr.upper())
            teams.append(team)
    return teams


def prefetch(
    league_keys: list[str],
    store: LogoStore,
    session=None,
    workers: int = 4,
    pace: float = 0.05,
) -> dict[str, int]:
    """Download and prepare every team's logos. Returns {"nfl": ok, "nfl_failed": n, ...}.

    Keys: "<league>" counts teams that are ready, "<league>_failed" those that
    are not. Unknown league keys and failed enumerations count as one failure.
    """
    result: dict[str, int] = {}
    for key in league_keys:
        if key not in LEAGUES:
            log.error("unknown league %r", key)
            result[key] = 0
            result[f"{key}_failed"] = 1
            continue
        try:
            teams = fetch_teams(key, session=session)
        except Exception as e:
            log.error("could not list %s teams: %s", key, e)
            result[key] = 0
            result[f"{key}_failed"] = 1
            continue
        log.info("%s: %d teams", key, len(teams))

        def one(team: Team, key=key) -> bool:
            ok = store.prepare_sync(key, team)
            time.sleep(pace)
            return ok

        ok = failed = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for i, good in enumerate(pool.map(one, teams), 1):
                ok += good
                failed += not good
                if i % 25 == 0 or i == len(teams):
                    log.info("%s: %d/%d done (%d failed)", key, i, len(teams), failed)
        result[key] = ok
        result[f"{key}_failed"] = failed
    return result
