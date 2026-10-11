"""Display backends. The app hands every backend a finished 64x32 Pillow frame.

- "hardware": hzeller rpi-rgb-led-matrix (`rgbmatrix`), on the Pi.
- "emulator": RGBMatrixEmulator (browser page at http://localhost:8888).
- "headless": keeps the last frame in memory; used by snapshots and tests.

"auto" picks hardware when `rgbmatrix` imports, else the emulator.

Both matrix backends draw only on an offscreen canvas from CreateFrameCanvas()
via one SetImage() per frame, then SwapOnVSync(). No SetPixel/Fill on the
matrix object. SetImage is supported by RGBMatrixEmulator; if a binding ever
rejects it, we fall back to copying pixels onto the offscreen canvas.
"""

from __future__ import annotations

import logging
from typing import Any

from PIL import Image

log = logging.getLogger(__name__)


class Backend:
    name = "base"
    width = 64
    height = 32

    def show(self, frame: Image.Image) -> None:
        raise NotImplementedError

    def set_brightness(self, value: int) -> None:
        pass

    def close(self) -> None:
        pass


class HeadlessBackend(Backend):
    name = "headless"

    def __init__(self, width: int = 64, height: int = 32):
        self.width, self.height = width, height
        self.last: Image.Image | None = None
        self.brightness = 100
        self.frames_shown = 0

    def show(self, frame: Image.Image) -> None:
        self.last = frame.copy()
        self.frames_shown += 1

    def set_brightness(self, value: int) -> None:
        self.brightness = value


class MatrixBackend(Backend):
    """Shared logic for rgbmatrix and RGBMatrixEmulator (same API)."""

    def __init__(self, module_name: str, matrix_opts: dict[str, Any], brightness: int):
        if module_name == "rgbmatrix":
            from rgbmatrix import RGBMatrix, RGBMatrixOptions  # type: ignore[import-not-found]
        else:
            from RGBMatrixEmulator import RGBMatrix, RGBMatrixOptions  # type: ignore

        self.name = "hardware" if module_name == "rgbmatrix" else "emulator"
        options = RGBMatrixOptions()
        for key, val in matrix_opts.items():
            if key == "brightness":
                continue
            if hasattr(options, key) or self.name == "hardware":
                try:
                    setattr(options, key, val)
                except (AttributeError, TypeError, ValueError) as e:
                    log.warning("matrix option %s=%r not accepted: %s", key, val, e)
            else:
                log.debug("emulator ignores matrix option %s", key)
        options.brightness = brightness
        self.matrix = RGBMatrix(options=options)
        self.width = self.matrix.width
        self.height = self.matrix.height
        self.canvas = self.matrix.CreateFrameCanvas()
        self._set_image_ok = True
        self._brightness = brightness
        log.info("%s backend ready (%dx%d)", self.name, self.width, self.height)

    def show(self, frame: Image.Image) -> None:
        if frame.mode != "RGB":
            frame = frame.convert("RGB")
        if self._set_image_ok:
            try:
                # unsafe=False: bounds-checked path, works across Pillow versions.
                self.canvas.SetImage(frame, 0, 0, unsafe=False)
            except (AttributeError, TypeError, ValueError) as e:
                log.warning("SetImage failed (%s); falling back to per-pixel copy", e)
                self._set_image_ok = False
        if not self._set_image_ok:
            self._copy_pixels(frame)
        # The canvas brightness must be set on the canvas we are about to show.
        self.canvas.brightness = self._brightness
        self.canvas = self.matrix.SwapOnVSync(self.canvas)

    def _copy_pixels(self, frame: Image.Image) -> None:
        # Fallback: writes to the offscreen canvas only (never the live matrix).
        data = frame.tobytes()
        w = frame.width
        set_px = self.canvas.SetPixel
        for i in range(0, len(data), 3):
            p = i // 3
            set_px(p % w, p // w, data[i], data[i + 1], data[i + 2])

    def set_brightness(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        if value != self._brightness:
            self._brightness = value
            self.matrix.brightness = value

    def close(self) -> None:
        try:
            self.canvas.Clear()
            self.canvas = self.matrix.SwapOnVSync(self.canvas)
        except Exception:  # noqa: BLE001 - best effort on shutdown
            pass


def hardware_available() -> bool:
    try:
        import rgbmatrix  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        return False
    return True


def create_backend(kind: str, matrix_opts: dict[str, Any], brightness: int) -> Backend:
    """kind: auto | hardware | emulator | headless."""
    width = int(matrix_opts.get("cols", 64)) * int(matrix_opts.get("chain_length", 1))
    height = int(matrix_opts.get("rows", 32)) * int(matrix_opts.get("parallel", 1))
    if kind == "headless":
        return HeadlessBackend(width, height)
    if kind == "auto":
        kind = "hardware" if hardware_available() else "emulator"
    if kind == "hardware":
        return MatrixBackend("rgbmatrix", matrix_opts, brightness)
    if kind == "emulator":
        return MatrixBackend("RGBMatrixEmulator", matrix_opts, brightness)
    raise ValueError(f"unknown backend {kind!r}")
