"""--profile: measure frame times, CPU and memory instead of guessing."""

from __future__ import annotations

import logging
import os
import resource
import sys
import time

log = logging.getLogger("sportsticker.profile")


def rss_mb() -> float:
    """Current resident memory in MB (Linux /proc), else peak RSS."""
    try:
        with open("/proc/self/statm") as f:
            pages = int(f.read().split()[1])
        return pages * os.sysconf("SC_PAGE_SIZE") / 1e6
    except (OSError, ValueError, IndexError):
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return peak / 1e6 if sys.platform == "darwin" else peak / 1e3


class Profiler:
    """Accumulates per-frame timings and logs a summary every `interval` seconds.

    render-thread CPU (time.thread_time) is our own work. Process CPU also
    includes rgbmatrix's panel refresh thread on the Pi, which is expected to
    use most of a core by itself; the two numbers are reported separately.
    """

    def __init__(self, enabled: bool, interval: float = 10.0):
        self.enabled = enabled
        self.interval = interval
        self._reset(time.monotonic())
        self.history: list[dict] = []

    def _reset(self, now: float) -> None:
        self.t0 = now
        self.thread0 = time.thread_time()
        self.proc0 = time.process_time()
        self.frames = 0
        self.compose: list[float] = []
        self.show: list[float] = []

    def record(self, compose_s: float, show_s: float) -> None:
        if not self.enabled:
            return
        self.frames += 1
        self.compose.append(compose_s)
        self.show.append(show_s)

    def tick(self) -> dict | None:
        if not self.enabled:
            return None
        now = time.monotonic()
        wall = now - self.t0
        if wall < self.interval:
            return None
        stats = {
            "frames": self.frames,
            "fps": self.frames / wall,
            "compose_avg_ms": 1000 * sum(self.compose) / max(1, len(self.compose)),
            "compose_max_ms": 1000 * max(self.compose, default=0),
            "show_avg_ms": 1000 * sum(self.show) / max(1, len(self.show)),
            "show_max_ms": 1000 * max(self.show, default=0),
            "render_cpu_pct": 100 * (time.thread_time() - self.thread0) / wall,
            "process_cpu_pct": 100 * (time.process_time() - self.proc0) / wall,
            "rss_mb": rss_mb(),
        }
        log.info(
            "frames=%d (%.1f/s) compose avg %.2f max %.2f ms | show avg %.2f max %.2f ms | "
            "render-thread CPU %.1f%% | process CPU %.1f%% | RSS %.1f MB",
            stats["frames"],
            stats["fps"],
            stats["compose_avg_ms"],
            stats["compose_max_ms"],
            stats["show_avg_ms"],
            stats["show_max_ms"],
            stats["render_cpu_pct"],
            stats["process_cpu_pct"],
            stats["rss_mb"],
        )
        self.history.append(stats)
        self._reset(now)
        return stats
