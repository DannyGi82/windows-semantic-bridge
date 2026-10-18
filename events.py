"""Lightweight process-scoped WinEvent observer; no input hooks or code injection."""
from collections import deque
import ctypes
from ctypes import wintypes
import sys
import threading
import time

class EventBuffer:
    def __init__(self, limit=256, quiet_ms=120):
        if limit < 1: raise ValueError("limit must be positive")
        self._events=deque(maxlen=limit)
        self._seen={}
        self.quiet_ms=quiet_ms
        self._lock=threading.Lock()

    def push(self, pid, event, hwnd, clock_ms=None):
        if not pid: return
        now=clock_ms if clock_ms is not None else time.monotonic_ns()/1_000_000
        key=(pid,event,hwnd)
        with self._lock:
            last=self._seen.get(key)
            if last is not None and now-last<self.quiet_ms: return
            self._seen[key]=now
            if len(self._seen)>2048:
                self._seen={k:v for k,v in self._seen.items() if now-v<3000}
            self._events.append({"pid":pid,"event":event,"hwnd":hwnd,"at_ms":round(now)})

    def drain(self):
        with self._lock:
            rows=list(self._events)
            self._events.clear()
            return rows

class WindowsEventWatcher:
    """Subscribe only to specified process; background hook thread does not touch UI."""
    def __init__(self, buffer=None):
        self.buffer=buffer or EventBuffer()
        self._stop=threading.Event()
        self._ready=threading.Event()
        self._thread=None
        self.pid=None
        self.error=None

    def start(self,pid: int):
        if sys.platform!='win32':
            raise RuntimeError("Windows only")
        pid=int(pid)
        if pid < 1: raise ValueError("PID must be positive")
        self.stop()
        self.pid=pid
        self.error=None
        self._stop.clear()
        self._ready.clear()
        self._thread=threading.Thread(target=self._run,name="semantic-win-events",daemon=True)
        self._thread.start()
        if not self._ready.wait(3):
            self.stop()
            raise RuntimeError("WinEvent observer not ready")
        if self.error:
            error=self.error
            self.stop()
            raise RuntimeError(error)

    def _run(self):
        u=ctypes.WinDLL("user32", use_last_error=True)
        PROC=ctypes.WINFUNCTYPE(None,wintypes.HANDLE,wintypes.DWORD,wintypes.HWND,
                              ctypes.c_long,ctypes.c_long,wintypes.DWORD,wintypes.DWORD)
        u.SetWinEventHook.argtypes=[wintypes.DWORD,wintypes.DWORD,wintypes.HMODULE,PROC,
                                    wintypes.DWORD,wintypes.DWORD,wintypes.DWORD]
        u.SetWinEventHook.restype=wintypes.HANDLE
        u.UnhookWinEvent.argtypes=[wintypes.HANDLE]
        u.PeekMessageW.argtypes=[ctypes.POINTER(wintypes.MSG),wintypes.HWND,wintypes.UINT,
                                 wintypes.UINT,wintypes.UINT]
        u.PeekMessageW.restype=wintypes.BOOL
        u.DispatchMessageW.argtypes=[ctypes.POINTER(wintypes.MSG)]
        u.TranslateMessage.argtypes=[ctypes.POINTER(wintypes.MSG)]
        pid=self.pid
        def on_event(_hook,event,hwnd,_obj,_child,_thread,_stamp):
            self.buffer.push(pid,int(event),int(hwnd or 0))
        callback=PROC(on_event)
        # EVENT_OBJECT_CREATE through VALUECHANGE covers create/remove/show/focus/name/value.
        # WINEVENT_OUTOFCONTEXT=0; WINEVENT_SKIPOWNPROCESS=2.
        h=u.SetWinEventHook(0x8000,0x800E,None,callback,pid,0,2)
        if not h:
            self.error="SetWinEventHook refused; win32="+str(ctypes.get_last_error())
            self._ready.set()
            return
        self._ready.set()
        try:
            msg=wintypes.MSG()
            while not self._stop.is_set():
                while u.PeekMessageW(ctypes.byref(msg),None,0,0,1):
                    if msg.message != 0x0012:
                        u.TranslateMessage(ctypes.byref(msg))
                        u.DispatchMessageW(ctypes.byref(msg))
                self._stop.wait(0.03)
        finally:
            u.UnhookWinEvent(h)

    def drain(self):return self.buffer.drain()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread=None
        self.pid=None
        self.buffer.drain()

def foreground_pid():
    if sys.platform!='win32': raise RuntimeError("Windows only")
    user32=ctypes.WinDLL("user32",use_last_error=True)
    user32.GetForegroundWindow.restype=wintypes.HWND
    handle=user32.GetForegroundWindow()
    if not handle: raise RuntimeError("no foreground window")
    pid=wintypes.DWORD()
    user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId(handle,ctypes.byref(pid))
    if not pid.value: raise RuntimeError("foreground PID unavailable")
    return pid.value
