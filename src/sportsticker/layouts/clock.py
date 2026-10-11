"""Clock and date screen, shown when no enabled league has games today."""

from __future__ import annotations

from datetime import datetime

from PIL import Image

from .base import blank, draw_centered, font

TIME_COLOR = (255, 170, 60)
DATE_COLOR = (150, 150, 150)
NOTE_COLOR = (70, 70, 70)


def render_clock(now_local: datetime, note: str = "NO GAMES TODAY") -> Image.Image:
    img = blank()
    hour = now_local.hour % 12 or 12
    t = f"{hour}:{now_local.minute:02d}"
    big = font("9x18B")
    draw_centered(img, big, 31.5, 2, t, TIME_COLOR)
    ampm = "AM" if now_local.hour < 12 else "PM"
    # AM/PM tucked to the right of the time, bottom-aligned with the digits
    left, right = big.ink_bounds(t)
    end_x = round(31.5 - (right - left) / 2) + (right - left) + 2
    small = font("4x6")
    if end_x + small.text_width(ampm) <= 64:
        small.draw_cap(img, end_x, 2 + big.cap_height - small.cap_height, ampm, DATE_COLOR)
    date = now_local.strftime("%a %b %-d").upper()
    draw_centered(img, font("5x7"), 31.5, 16, date, DATE_COLOR)
    if note:
        draw_centered(img, font("tom-thumb"), 31.5, 26, note, NOTE_COLOR)
    return img


def clock_image(now_local: datetime, note: str = "NO GAMES TODAY") -> Image.Image:
    return render_clock(now_local, note)


__all__ = ["render_clock", "Image"]
