"""Windows process identity: PID plus immutable creation FILETIME.

Prevents observing a different process when Windows recycles a numeric PID.
"""
import ctypes
from ctypes import wintypes
import sys

class ProcessUnavailableError(ProcessLookupError):
    """OS definitively reported a terminated or nonexistent process."""


def classify_open_error(code: int):
    """Translate Win32 OpenProcess failures without confusing access denial with exit."""
    if code == 87:  # ERROR_INVALID_PARAMETER: no such PID
        raise ProcessUnavailableError("process no longer exists")
    if code == 5:   # ERROR_ACCESS_DENIED: may still be running
        raise PermissionError("process identity access denied")
    raise OSError(code, "process identity unavailable; refusing stale cleanup")


class FILETIME(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

def process_identity(pid: int) -> int:
    if sys.platform != "win32":
        raise RuntimeError("Windows process identity requires Windows")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid < 1:
        raise ValueError("PID must be a positive integer")
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.OpenProcess.restype = wintypes.HANDLE
    k.GetProcessTimes.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME),
        ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME)]
    k.GetProcessTimes.restype = wintypes.BOOL
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        classify_open_error(ctypes.get_last_error())
    try:
        created, exited, kernel, user = FILETIME(), FILETIME(), FILETIME(), FILETIME()
        if not k.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                 ctypes.byref(kernel), ctypes.byref(user)):
            raise OSError(ctypes.get_last_error(), "unable to validate process creation timestamp")
        if exited.high != 0 or exited.low != 0:
            raise ProcessUnavailableError("PID refers to a terminated process")
        return (int(created.high) << 32) | int(created.low)
    finally:
        k.CloseHandle(handle)