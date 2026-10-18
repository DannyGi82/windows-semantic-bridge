"""Read-only semantic bridge: bounded state, PID identity, event reconciliation."""
from functools import wraps
import threading
import time

from state import StateTracker


def serialized(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


class SemanticBridge:
    def __init__(self, rpc, watcher, reconcile_seconds=20, identity_of=None):
        self._lock = threading.RLock()
        self.rpc = rpc
        self.watcher = watcher
        self.identity_of = identity_of
        self._identity = None
        self.reconcile_seconds = reconcile_seconds
        self.tracker = StateTracker()
        self.pid = None
        self.last_error = None

    @serialized
    def watch(self, pid: int):
        pid = int(pid)
        if pid < 1:
            raise ValueError("PID must be positive")
        self.stop()
        identity = self.identity_of(pid) if self.identity_of else None
        self.watcher.start(pid)
        self._identity = identity
        self.pid = pid
        return {"watching_pid": pid, "read_only": True, "revision": 0}

    def _validate_identity(self):
        if self.pid is None:
            raise PermissionError("no watched target")
        if self.identity_of is not None:
            try:
                current = self.identity_of(self.pid)
            except Exception:
                self.stop()
                raise RuntimeError("watched process unavailable; observation stopped") from None
            if current != self._identity:
                self.stop()
                raise RuntimeError("watched process identity changed; observation stopped")

    @serialized
    def poll(self, force: bool = False):
        if self.pid is None:
            raise PermissionError("must select target with watch(pid) first")
        self._validate_identity()
        events = self.watcher.drain()
        due = (self.tracker.stale or self.tracker.revision == 0
               or (time.monotonic() - self.tracker.last_refresh) >= self.reconcile_seconds)
        if not (force or events or due):
            return {"revision": self.tracker.revision, "unchanged": True, "events": 0}
        try:
            text = self.rpc.text(str(self.pid))
            self._validate_identity()
            delta = self.tracker.apply(text)
            self.last_error = None
            delta["events"] = len(events)
            delta["unchanged"] = not delta["changed"]
            return delta
        except Exception as exc:
            self.last_error = type(exc).__name__
            self.tracker.mark_stale(self.last_error)
            raise

    @serialized
    def state(self):
        self._validate_identity()
        return {"revision": self.tracker.revision, "pid": self.pid,
                "text": self.tracker.get_current()}

    @serialized
    def changes_since(self, revision: int):
        self._validate_identity()
        return self.tracker.changes_since(revision)

    @serialized
    def status(self):
        return {"watching_pid": self.pid, "read_only": True,
                "revision": self.tracker.revision, "last_error": self.last_error,
                "snapshot_ready": bool(self.tracker.current_text) and not self.tracker.stale,
                "stale": self.tracker.stale}

    @serialized
    def capture(self):
        self._validate_identity()
        image = self.rpc.capture(str(self.pid))
        self._validate_identity()
        return image

    @serialized
    def stop(self):
        self.watcher.stop()
        cleanup = getattr(self.rpc,"close_state_worker",None)
        if cleanup is not None:
            cleanup()
        self.pid = None
        self._identity = None
        self.last_error = None
        self.tracker.reset()

    @serialized
    def close(self):
        self.stop()
        self.rpc.close()