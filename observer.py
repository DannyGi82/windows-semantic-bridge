"""Event-triggered, read-only semantic observation in a bounded local thread.

No GUI input, network listener, data persistence, or automatic Windows startup.
"""
from __future__ import annotations

import threading
import time


class PassiveObserver:
    def __init__(self, bridge, check_interval: float = 0.2):
        if not 0.02 <= check_interval <= 60:
            raise ValueError("check_interval out of range")
        self.bridge = bridge
        self.check_interval = check_interval
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._thread = None
        self._last_error = None
        self._refreshes = 0
        self._events_seen = 0
        self._last_refresh_ms = None

    def start(self, pid: int) -> dict:
        with self._lock:
            self.stop()
            result = self.bridge.watch(pid)
            self._cancel.clear()
            self._last_error = None
            self._refreshes = 0
            self._events_seen = 0
            self._last_refresh_ms = None
            self._thread = threading.Thread(target=self._run, daemon=True,
                                            name="semantic-bridge-passive")
            self._thread.start()
            return result | {"running": True}

    def _run(self) -> None:
        backoff = self.check_interval
        while not self._cancel.is_set():
            try:
                started = time.perf_counter()
                result = self.bridge.poll(force=False)
                self._events_seen += result.get("events", 0)
                if "changed" in result:
                    self._refreshes += 1
                    self._last_refresh_ms = round(1000 * (time.perf_counter() - started), 2)
                self._last_error = None
                backoff = self.check_interval
            except Exception as exc:
                self._last_error = type(exc).__name__
                if self.bridge.status()["watching_pid"] is None:
                    return
                backoff = min(5.0, max(0.5, backoff * 2))
            self._cancel.wait(backoff)

    def changes_since(self, revision: int) -> dict:
        return self.bridge.changes_since(revision)

    def status(self) -> dict:
        result = self.bridge.status()
        result["running"] = bool(self._thread and self._thread.is_alive())
        result["refreshes"] = self._refreshes
        result["events_seen"] = self._events_seen
        result["last_refresh_ms"] = self._last_refresh_ms
        if self._last_error:
            result["last_error"] = self._last_error
        return result

    def stop(self) -> dict:
        with self._lock:
            self._cancel.set()
            thread = self._thread
            if thread is not None:
                thread.join(timeout=12)
                if thread.is_alive():
                    raise RuntimeError("observer did not terminate; stop not confirmed")
            self._thread = None
            self.bridge.close()
            self._last_error = None
            return {"stopped": True, "running": False}
