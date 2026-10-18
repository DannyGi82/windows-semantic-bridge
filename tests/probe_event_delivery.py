"""Windows-only noninvasive WinEvent delivery probe: self-owned hidden test window.

No mouse/keyboard injection, network access, files modified or user windows opened.
"""
import ctypes
from ctypes import wintypes
import os
import subprocess
import sys
import time

from events import WindowsEventWatcher

def parse_ready(line: str, launcher_pid: int) -> int:
    parts = line.strip().split()
    if len(parts) < 2 or parts[0] != "READY":
        raise ValueError("producer did not report its actual PID")
    pid = int(parts[1])
    if pid <= 0:
        raise ValueError("invalid producer PID")
    return pid

def producer() -> None:
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p
    ]
    u.CreateWindowExW.restype = wintypes.HWND
    u.NotifyWinEvent.argtypes = [wintypes.DWORD, wintypes.HWND, ctypes.c_long, ctypes.c_long]
    u.NotifyWinEvent.restype = None
    u.DestroyWindow.argtypes = [wintypes.HWND]
    u.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
    u.PeekMessageW.restype = wintypes.BOOL
    # Zero style creates an invisible STATIC control owned by this test process.
    offscreen = "--offscreen" in sys.argv
    window = u.CreateWindowExW(0x80 if offscreen else 0, "STATIC", "semantic-lab-internal",
                               0x90000000 if offscreen else 0,
                               -32000 if offscreen else 0, -32000 if offscreen else 0, 16, 16, None, None, None, None)
    if not window:
        print("ERROR", flush=True)
        return
    print("READY " + str(os.getpid()) + (" " + str(int(window)) if "--print-hwnd" in sys.argv else ""), flush=True)
    if sys.stdin.readline().strip() == "EMIT":
        for index in range(4):
            u.NotifyWinEvent(0x800C, window, 0, 0)  # EVENT_OBJECT_NAMECHANGE
            time.sleep(0.18)
        msg = wintypes.MSG()
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            while u.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                u.TranslateMessage(ctypes.byref(msg))
                u.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.02)
    u.DestroyWindow(window)

def main() -> int:
    if sys.platform != "win32":
        print("SKIP_NOT_WINDOWS")
        return 0
    args = [sys.executable, os.path.abspath(__file__), "--producer"]
    child = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
    watcher = WindowsEventWatcher()
    try:
        ready = child.stdout.readline().strip()
        if not ready.startswith("READY "):
            print("PRODUCER_NOT_READY")
            return 2
        target_pid = parse_ready(ready, child.pid)
        watcher.start(target_pid)
        child.stdin.write("EMIT\n")
        child.stdin.flush()
        child.wait(timeout=5)
        time.sleep(.25)
        events = watcher.drain()
        print("launcher_pid", child.pid)
        print("target_pid", target_pid)
        print("event_count", len(events))
        print("namechange_count", sum(e["event"] == 0x800C for e in events))
        print("no_content_recorded", True)
        return 0 if sum(e["event"] == 0x800C for e in events) >= 2 else 3
    finally:
        watcher.stop()
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=3)
        child.stdin.close()
        child.stdout.close()

if __name__ == "__main__":
    if "--producer" in sys.argv:
        producer()
    else:
        sys.exit(main())
