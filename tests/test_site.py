import json
import re
from pathlib import Path

from PIL import Image

from sportsticker.bdf import load_font
from sportsticker.preview import grid_view, led_view
from sportsticker.site import manifest_json, render_index, write_index

W, H = 64, 32


def pixels_hex(img: Image.Image) -> str:
    return img.convert("RGB").tobytes().hex()


def make_frame(label: str, color: tuple[int, int, int], bar: int = 20) -> Image.Image:
    img = Image.new("RGB", (W, H), (0, 0, 0))
    font = load_font("6x10")
    font.draw(img, 2, 2, label, color)
    load_font("4x6").draw(img, 2, 15, "Q3 4:12", (255, 255, 255))
    for x in range(2, 2 + bar):
        for y in (25, 26):
            img.putpixel((x, y), (0, 200, 90))
    for x in range(40, 62):
        img.putpixel((x, 28), (255, 40, 40))
    return img


def build_demo(out_dir: Path) -> dict:
    """Write PNGs for four synthetic slides and return the matching manifest."""
    for sub in ("raw", "led", "grid"):
        (out_dir / sub).mkdir(parents=True, exist_ok=True)
    specs = [
        ("a-01-nfl-buf-kc", "BUF @ KC", "Q3 4:12 · NFL", "a", "BUF 24", (255, 200, 0), 6),
        ("a-02-nba-bos-nyk", "BOS @ NYK", "Final · NBA", "a", "BOS 101", (0, 220, 120), 6),
        ("b-01-nhl-bos-tor", "BOS vs TOR", "P2 12:40 · NHL", "b", "BOS 2", (255, 120, 40), 5),
        ("c-01-epl-ars-che", "ARS v CHE", "Today 12:30 · EPL", "c", "ARS", (80, 160, 255), 4),
    ]
    items = []
    for n, (id_, title, sub, layout, label, color, secs) in enumerate(specs):
        img = make_frame(label, color, bar=10 + n * 10)
        img.save(out_dir / "raw" / f"{id_}.png")
        led_view(img).save(out_dir / "led" / f"{id_}.png")
        grid_view(img).save(out_dir / "grid" / f"{id_}.png")
        items.append(
            {
                "id": id_,
                "title": title,
                "subtitle": sub,
                "layout": layout,
                "led": f"led/{id_}.png",
                "grid": f"grid/{id_}.png",
                "raw": f"raw/{id_}.png",
                "duration": secs,
                "pixels": pixels_hex(img),
            }
        )
    return {
        "title": "Sportsticker preview",
        "generated_at": "2026-10-11T19:30:00-04:00",
        "source": "fake-live",
        "timezone": "America/New_York",
        "logos": False,
        "note": "Synthetic demo frames, not real games.",
        "width": W,
        "height": H,
        "sections": [
            {
                "title": "Current rotation (layout A)",
                "description": "What the panel shows right now.",
                "items": items[:2],
            },
            {"title": "Other layouts", "items": items[2:]},
        ],
        "comparisons": [
            {
                "title": "BUF @ KC",
                "images": {"a": items[0]["led"], "b": items[2]["led"], "c": items[3]["led"]},
            }
        ],
    }


def embedded_manifest(page: str) -> dict:
    m = re.search(r"const MANIFEST = (.*?);</script>", page, re.S)
    assert m, "manifest script not found"
    return json.loads(m.group(1).replace("<\\/", "</"))


def test_write_index_embeds_manifest(tmp_path):
    manifest = build_demo(tmp_path)
    manifest["sections"] = [
        {"title": "S", "items": manifest["sections"][0]["items"]},
    ]
    path = write_index(tmp_path, manifest)
    assert path == tmp_path / "index.html"
    page = path.read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>")
    assert "<canvas" in page or '"canvas"' in page  # inspector draws into a canvas
    assert embedded_manifest(page) == manifest
    # self-contained: no absolute URLs, no external scripts/styles, no fetch()
    assert "http" not in page
    assert "fetch(" not in page
    assert "<script src" not in page
    assert "Logos are not shown on this public page" in page
    assert "Click any slide to inspect pixels" in page


def test_write_index_creates_dir_and_tolerates_minimal_manifest(tmp_path):
    out = tmp_path / "nested" / "site"
    path = write_index(out, {})
    assert path.exists()
    assert "Sportsticker preview" in path.read_text(encoding="utf-8")


def test_script_close_in_title_is_escaped():
    evil = "</script><script>alert(1)</script> <!-- x"
    manifest = {
        "title": evil,
        "note": evil,
        "sections": [{"title": evil, "items": [{"id": "x", "title": evil}]}],
    }
    page = render_index(manifest)
    # only the real script blocks may close a script element
    assert page.count("</script>") == 2
    assert "<script>alert(1)</script>" not in page
    assert "&lt;/script&gt;" in page  # <title>/<h1> are HTML-escaped
    assert "<\\/script>" in page
    assert "<!--" not in manifest_json(manifest)
    assert embedded_manifest(page) == manifest


def test_pixels_round_trip_in_page(tmp_path):
    img = make_frame("HI", (255, 0, 255))
    manifest = {"sections": [{"title": "S", "items": [{"id": "i", "pixels": pixels_hex(img)}]}]}
    page = write_index(tmp_path, manifest).read_text(encoding="utf-8")
    px = embedded_manifest(page)["sections"][0]["items"][0]["pixels"]
    assert len(px) == W * H * 3 * 2
    assert bytes.fromhex(px) == img.tobytes()


def test_demo_site_files_exist(tmp_path):
    manifest = build_demo(tmp_path)
    write_index(tmp_path, manifest)
    for sec in manifest["sections"]:
        for it in sec["items"]:
            for key in ("raw", "led", "grid"):
                assert (tmp_path / it[key]).exists()
                assert not it[key].startswith(("/", "http"))
