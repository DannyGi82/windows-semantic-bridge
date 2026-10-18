"""Bounded in-memory semantic snapshots and change sets; no disk persistence."""
from collections import Counter, deque
import re
import time

_EPHEMERAL = re.compile(r"\[e\d+\]")
_SPACES = re.compile(r"\s+")
MAX_SNAPSHOT_CHARS = 30_000

def normalize_line(line: str) -> str:
    """Remove ephemeral Munim handles but preserve roles/names/states."""
    return _SPACES.sub(" ", _EPHEMERAL.sub("[element]", line)).strip()

class StateTracker:
    def __init__(self, max_changes: int = 32, history_size: int = 32):
        if max_changes < 1 or history_size < 1:
            raise ValueError("positive bounds required")
        self.max_changes = max_changes
        self.history = deque(maxlen=history_size)
        self.current_text = ""
        self._previous = Counter()
        self._previous_lines = ()
        self.revision = 0
        self.last_refresh = 0.0
        self.stale = False

    def apply(self, text: str) -> dict:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("refusing empty/invalid semantic snapshot")
        if len(text) > MAX_SNAPSHOT_CHARS:
            raise ValueError("snapshot too large for bounded state")
        lines = [normalize_line(s) for s in text.splitlines() if s.strip()]
        new = Counter(lines)
        additions = list((new - self._previous).elements())
        removals = list((self._previous - new).elements())
        reordered = bool(self._previous_lines) and not (additions or removals) and tuple(lines) != self._previous_lines
        changed = self.revision == 0 or bool(additions or removals) or reordered
        if changed:
            self.revision += 1
        self._previous = new
        self._previous_lines = tuple(lines)
        self.current_text = text
        self.last_refresh = time.monotonic()
        self.stale = False
        delta = {
            "revision": self.revision,
            "changed": changed,
            "reordered": reordered,
            "added": additions[:self.max_changes],
            "removed": removals[:self.max_changes],
            "truncated": len(additions) > self.max_changes or len(removals) > self.max_changes,
        }
        if changed:
            self.history.append(delta)
        return delta

    def changes_since(self, revision: int) -> dict:
        if type(revision) is not int or revision < 0 or revision > self.revision:
            raise ValueError("revision must be an existing non-negative integer")
        if self.stale:
            raise RuntimeError("semantic state is stale; refresh required")
        earliest = self.history[0]["revision"] if self.history else self.revision
        return {
            "revision": self.revision,
            "gap": revision < earliest - 1,
            "changes": [change for change in self.history if change["revision"] > revision],
        }
    def mark_stale(self, reason: str) -> None:
        self.stale = True

    def get_current(self) -> str:
        if self.stale:
            raise RuntimeError("semantic state is stale; refresh required")
        if not self.current_text:
            raise RuntimeError("no valid snapshot yet")
        return self.current_text

    def reset(self):
        self.current_text = ""
        self._previous.clear()
        self._previous_lines = ()
        self.revision = 0
        self.last_refresh = 0.0
        self.stale = False
        self.history.clear()
