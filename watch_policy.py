"""Fail-closed Windows session guard for deliberately selected watch PIDs.

Does not assert end-user intent; tools still must obtain explicit PID selection.
"""
import ctypes
from ctypes import wintypes
import os


def windows_session_of(pid):
    k=ctypes.WinDLL("kernel32",use_last_error=True)
    k.ProcessIdToSessionId.argtypes=[wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
    k.ProcessIdToSessionId.restype=wintypes.BOOL
    session=wintypes.DWORD()
    if not k.ProcessIdToSessionId(pid,ctypes.byref(session)):
        raise OSError(ctypes.get_last_error(),"unable to validate process session")
    return int(session.value)


def require_same_session(pid, *, current_pid=None, session_of=None):
    if type(pid) is not int or not 1<=pid<2**31:
        raise ValueError("invalid watch PID")
    if current_pid is None:
        current_pid=os.getpid()
    if session_of is None:
        session_of=windows_session_of
    try:
        own=session_of(current_pid)
        target=session_of(pid)
    except Exception:
        raise PermissionError("target session cannot be verified") from None
    if target!=own:
        raise PermissionError("target must belong to broker Windows session")
    return pid
