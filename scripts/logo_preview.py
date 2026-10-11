#!/usr/bin/env python3
"""Contact sheet of team logos as they will look on the LED panel.

    python scripts/logo_preview.py --leagues nfl,nba --teams KC,OKC --out snapshots/logos
    python scripts/logo_preview.py --teams nfl:KC,ncaab:CREI,epl:TOT --out snapshots/logos

Each team gets a row: abbreviation, then logo vs logoDark at 16 px and 24 px,
each drawn through preview.led_view (round LEDs, 10x) on a 26x26 LED tile with
its readability score underneath. The variant "auto" picks is boxed in green.

Logos are team trademarks: they are cached under --cache-dir (default
~/.cache/sportsticker/logos) and the sheet goes to --out (snapshots/ is
gitignored). Never point either into a tracked directory.
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from sportsticker.config import LogoConfig
from sportsticker.logos import LogoStore, fetch_teams, readability
from sportsticker.models import LEAGUES, Team
from sportsticker.preview import led_view

SIZES = (16, 24)
TILE = 26  # LEDs per tile side
SCALE = 10
PAD = 14
LABEL_W = 120
GREEN = (60, 230, 90)
GRAY = (150, 150, 150)
BG = (12, 12, 12)


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--leagues", default="", help="comma list, e.g. nfl,nba (default: all)")
    ap.add_argument(
        "--teams", default="", help="comma list of ABBR or league:ABBR, e.g. KC,nba:OKC,epl:TOT"
    )
    ap.add_argument("--out", default="snapshots/logos", help="output directory")
    ap.add_argument("--name", default="", help="sheet file name (default: logos_<time>.png)")
    ap.add_argument("--cache-dir", default=None, help="logo cache (default: configured cache)")
    ap.add_argument("--tmp-cache", action="store_true", help="use a throwaway cache directory")
    ap.add_argument("--max-teams", type=int, default=24, help="cap rows when listing whole leagues")
    return ap.parse_args(argv)


def resolve_teams(leagues: list[str], wanted: list[str], max_teams: int) -> list[tuple[str, Team]]:
    """Find the requested teams on ESPN. `wanted` entries are ABBR or league:ABBR."""
    wanted_by_league: dict[str, set[str]] = {}
    anywhere: set[str] = set()
    for item in wanted:
        if ":" in item:
            lg, abbr = item.split(":", 1)
            wanted_by_league.setdefault(lg.lower(), set()).add(abbr.upper())
        else:
            anywhere.add(item.upper())
    search = list(leagues)
    for lg in wanted_by_league:
        if lg not in search:
            search.append(lg)
    if not search:
        search = list(LEAGUES)

    found: list[tuple[str, Team]] = []
    matched: set[tuple[str, str]] = set()
    for lg in search:
        if lg not in LEAGUES:
            sys.exit(f"unknown league {lg!r}; choose from {', '.join(LEAGUES)}")
        names = anywhere | wanted_by_league.get(lg, set())
        teams = fetch_teams(lg)
        picked = [t for t in teams if t.abbr.upper() in names] if wanted else teams[:max_teams]
        for t in picked:
            if (lg, t.abbr.upper()) not in matched:
                matched.add((lg, t.abbr.upper()))
                found.append((lg, t))
    # keep the order the user typed when explicit
    if wanted:
        order = {w.split(":")[-1].upper(): i for i, w in enumerate(wanted)}
        found.sort(key=lambda lt: order.get(lt[1].abbr.upper(), 99))
    missing = [
        w for w in wanted if w.split(":")[-1].upper() not in {t.abbr.upper() for _, t in found}
    ]
    for w in missing:
        print(f"warning: team {w!r} not found", file=sys.stderr)
    return found


def tile(entry, chosen: bool, font) -> Image.Image:
    """One LED tile (+ score caption) for a prepared (rgb, mask) logo, or a 'none' marker."""
    w = TILE * SCALE
    cap = 30
    out = Image.new("RGB", (w, w + cap), BG)
    d = ImageDraw.Draw(out)
    if entry is None:
        d.text((w // 2, w // 2), "n/a", fill=GRAY, font=font, anchor="mm")
        return out
    img, mask = entry
    frame = Image.new("RGB", (TILE, TILE), (0, 0, 0))
    frame.paste(
        img,
        ((TILE - img.width) // 2, (TILE - img.height) // 2),
        mask.point(lambda a: 255 if a >= 128 else 0),
    )
    out.paste(led_view(frame, scale=SCALE), (0, 0))
    score = readability(img, mask)
    d.text((6, w + 4), f"{score * 100:5.1f}  {img.width}x{img.height}", fill=GRAY, font=font)
    if chosen:
        d.rectangle((0, 0, w - 1, w + cap - 1), outline=GREEN, width=4)
        d.text((w - 8, w + 4), "AUTO", fill=GREEN, font=font, anchor="ra")
    return out


def team_row(store: LogoStore, league: str, team: Team, font, big) -> Image.Image:
    abbr = team.abbr.upper()
    chosen = store.chosen_variant(league, abbr)
    tw = TILE * SCALE
    heads = [f"{v} {s}px" for s in SIZES for v in ("logo", "dark")]
    row = Image.new("RGB", (LABEL_W + len(heads) * (tw + PAD), 22 + tw + 30), BG)
    d = ImageDraw.Draw(row)
    d.text((8, 40), abbr, fill=(255, 255, 255), font=big)
    d.text((8, 78), league, fill=GRAY, font=font)
    x = LABEL_W
    i = 0
    for size in SIZES:
        for variant in ("logo", "dark"):
            d.text((x + 4, 2), heads[i], fill=GRAY, font=font)
            entry = store.get_variant(league, abbr, size, variant)
            row.paste(tile(entry, chosen == variant, font), (x, 22))
            x += tw + PAD
            i += 1
    return row


def build_sheet(store: LogoStore, rows: list[tuple[str, Team]]) -> Image.Image:
    font, big = _font(15), _font(30)
    imgs = [team_row(store, lg, t, font, big) for lg, t in rows]
    cols = 1 if len(imgs) <= 8 else 2
    per_col = -(-len(imgs) // cols)
    cw, ch = imgs[0].size
    sheet = Image.new("RGB", (cols * cw + (cols - 1) * 30 + 2 * PAD, per_col * ch + 2 * PAD), BG)
    for i, im in enumerate(imgs):
        c, r = divmod(i, per_col)
        sheet.paste(im, (PAD + c * (cw + 30), PAD + r * ch))
    return sheet


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    leagues = [s.strip().lower() for s in args.leagues.split(",") if s.strip()]
    wanted = [s.strip() for s in args.teams.split(",") if s.strip()]
    rows = resolve_teams(leagues, wanted, args.max_teams)
    if not rows:
        print("no teams matched", file=sys.stderr)
        return 1

    tmp = tempfile.TemporaryDirectory() if args.tmp_cache else None
    cache = Path(tmp.name) if tmp else Path(args.cache_dir or LogoConfig().cache_dir).expanduser()
    store = LogoStore(cache, SIZES, variant="auto")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda lt: store.prepare_sync(*lt), rows))
    for (lg, t), ok in zip(rows, results, strict=True):
        if not ok:
            print(f"warning: no logo for {lg}/{t.abbr}", file=sys.stderr)

    sheet = build_sheet(store, rows)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / (args.name or f"logos_{datetime.now():%Y%m%d_%H%M%S}.png")
    sheet.save(path)
    print(f"{path.resolve()}  ({sheet.width}x{sheet.height})")
    if tmp:
        tmp.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
