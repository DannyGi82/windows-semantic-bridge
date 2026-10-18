"""Fail-closed gate for a test-owned fixture; NOT VisualGuard authorization.

Only the offline test harness can supply the test allow decision. This class
is not exposed through MCP and cannot act on arbitrary desktop windows.
"""
from __future__ import annotations

class UnsafeTarget(PermissionError):
    pass


class LabFixtureGate:
    def __init__(self, *, pid, hwnd, identity_at_launch, identity_of,
                 owner_pid_of, guard_check=None, cancelled=None, write=None):
        self._pid = pid
        self._hwnd = hwnd
        self._identity = identity_at_launch
        self._identity_of = identity_of
        self._owner_pid_of = owner_pid_of
        self._guard_check = guard_check
        self._cancelled = cancelled
        self._aborted = False
        self._write = write

    def _authorize(self):
        if self._aborted:
            raise UnsafeTarget("fixture action cancelled (latched)")
        try:
            if self._cancelled is not None and self._cancelled() is not False:
                self._aborted = True
                raise UnsafeTarget("fixture action cancelled")
        except UnsafeTarget:
            raise
        except Exception:
            self._aborted = True
            raise UnsafeTarget("fixture cancellation state unavailable") from None
        try:
            allowed = self._guard_check is not None and self._guard_check() is True
        except Exception:
            allowed = False
        if not allowed:
            raise UnsafeTarget("fixture authorization unavailable or denied")

    def _verify_ownership(self):
        try:
            if self._identity_of(self._pid) != self._identity:
                raise UnsafeTarget("fixture process identity changed")
            if self._owner_pid_of(self._hwnd) != self._pid:
                raise UnsafeTarget("fixture window owner changed")
        except UnsafeTarget:
            raise
        except Exception:
            raise UnsafeTarget("fixture process identity/owner could not be checked") from None

    def set_value(self, text: str):
        if not isinstance(text, str) or not text.startswith("LAB-") or len(text) > 48:
            raise UnsafeTarget("fixture values must be short LAB- prefixed text")
        self._authorize()
        self._verify_ownership()
        if self._write is None:
            raise UnsafeTarget("no fixture writer connected")
        result = self._write(self._hwnd, text)
        # We cannot retroactively undo a completed action when cancellation arrives.
        # Never report success if its authorization or identity changed in flight.
        self._authorize()
        self._verify_ownership()
        if result is not True:
            raise UnsafeTarget("fixture semantic action not confirmed")
        return True
