"""Continuous local discovery so AuraLAN keeps learning with the UI closed."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from typing import Any

DEFAULT_INTERVAL_SECONDS = 60
MIN_INTERVAL_SECONDS = 15
MAX_INTERVAL_SECONDS = 3600


def configured_interval() -> int:
    """Return the configured monitoring interval; zero disables monitoring."""
    raw = os.environ.get("AURALAN_MONITOR_INTERVAL", str(DEFAULT_INTERVAL_SECONDS)).strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_INTERVAL_SECONDS

    if value <= 0:
        return 0
    return max(MIN_INTERVAL_SECONDS, min(value, MAX_INTERVAL_SECONDS))


class BackgroundMonitor:
    """Run one bounded snapshot refresh periodically in a daemon thread."""

    def __init__(
        self,
        collector: Callable[..., dict[str, Any]],
        *,
        interval_seconds: int | None = None,
        after_collect: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.collector = collector
        self.after_collect = after_collect
        self.interval_seconds = configured_interval() if interval_seconds is None else int(interval_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last_attempt_at: int | None = None
        self._last_success_at: int | None = None
        self._last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return self.interval_seconds > 0

    def start(self) -> None:
        if not self.enabled or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="auralan-background-monitor",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=timeout)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.enabled,
                "interval_seconds": self.interval_seconds,
                "running": bool(self._thread and self._thread.is_alive()),
                "last_attempt_at": self._last_attempt_at,
                "last_success_at": self._last_success_at,
                "last_error": self._last_error,
            }

    def run_once(self) -> bool:
        now = int(time.time())
        with self._lock:
            self._last_attempt_at = now

        try:
            snapshot = self.collector(force=True)
            if self.after_collect:
                self.after_collect(snapshot)
        except Exception as exc:
            with self._lock:
                self._last_error = type(exc).__name__
            return False

        with self._lock:
            self._last_success_at = int(time.time())
            self._last_error = None
        return True

    def _run(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            if self._stop.wait(self.interval_seconds):
                break
