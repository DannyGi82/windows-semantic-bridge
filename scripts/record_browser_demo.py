#!/usr/bin/env python3
"""Capture actual Chrome window chrome (tabs + address bar) while exercising Browser Lane.

Records a disposable test page in a freshly created Chrome profile. This demo
temporarily displays its *own* browser window to capture browser chrome, then
restores the previously active application. Unlike a CDP Page screenshot, an
OS window capture includes Chrome tabs and address bar. The recorder refuses
to save any frame unless the new Chrome window is in the foreground.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

from PIL import Image, ImageDraw, ImageFont, ImageGrab, ImageStat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from browser_lane.cdp_lane import BrowserLane, CDP, _atomic_json  # noqa: E402
from browser_lane.process_id import process_identity  # noqa: E402

FIXTURE = Path(__file__).with_name("demo_fixture.html")
OUTPUT = ROOT / "assets"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
USER32 = ctypes.windll.user32
ENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

USER32.GetForegroundWindow.restype = wintypes.HWND
USER32.SetForegroundWindow.argtypes = [wintypes.HWND]
USER32.SetForegroundWindow.restype = wintypes.BOOL
USER32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
USER32.IsWindowVisible.argtypes = [wintypes.HWND]
USER32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?", 1)[0] not in ("/", "/docs", "/verified"):
            self.send_error(404)
            return
        data = FIXTURE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass

def font(size, bold=False):
    filename = "segoeuib.ttf" if bold else "segoeui.ttf"
    candidate = Path("C:/Windows/Fonts") / filename
    return ImageFont.truetype(str(candidate), size) if candidate.exists() else ImageFont.load_default()

def find_window(pid):
    windows = []

    @ENUM
    def check(hwnd, _):
        current = wintypes.DWORD()
        USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(current))
        if current.value == pid and USER32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(128)
            USER32.GetClassNameW(hwnd, buf, len(buf))
            if buf.value.startswith("Chrome_WidgetWin"):
                windows.append(hwnd)
        return True

    USER32.EnumWindows(check, 0)
    if len(windows) != 1:
        raise RuntimeError(f"Expected exactly one private Chrome window, found {len(windows)}")
    return windows[0]

def chrome_bounds(hwnd):
    rect = RECT()
    # DWM extended frame bounds exclude most invisible resize margins.
    try:
        status = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
        if status != 0:
            USER32.GetWindowRect(hwnd, ctypes.byref(rect))
    except (AttributeError, OSError):
        USER32.GetWindowRect(hwnd, ctypes.byref(rect))

    # Inside the window edges: never show desktop or an application behind it.
    bounds = (rect.left + 22, rect.top + 11, rect.right - 12, rect.bottom - 12)
    if bounds[2] - bounds[0] < 700 or bounds[3] - bounds[1] < 500:
        raise RuntimeError("Unsafe crop, browser window too small")
    return bounds

def screenshot(hwnd):
    # Never capture the desktop if our *exact* new Chrome window is not focused.
    USER32.SetForegroundWindow(hwnd)
    time.sleep(.13)
    if USER32.GetForegroundWindow() != hwnd:
        raise RuntimeError("Foreground window is not the isolated Chrome instance")
    bounds = chrome_bounds(hwnd)
    image = ImageGrab.grab(bbox=bounds, all_screens=True).convert("RGB")
    if USER32.GetForegroundWindow() != hwnd:
        raise RuntimeError("Foreground switched during screenshot; discarding frame")
    if max(ImageStat.Stat(image.resize((100, 64))).stddev) < 7:
        raise RuntimeError("Browser screenshot appears blank/invalid")
    return image.resize((1024, 620), Image.Resampling.LANCZOS)

def decorate(frame, heading, count):
    result = Image.new("RGB", (1050, 700), "#081222")
    result.paste(frame, (13, 14))
    d = ImageDraw.Draw(result)
    d.text((18, 649), heading, font=font(20, True), fill="#ecf7ff")
    d.text((18, 679), f"CHROME • ISOLATED PROFILE • {count} OWNED TAB{'S' if count != 1 else ''} • REAL OS CAPTURE",
           font=font(11), fill="#54cce1")
    return result

def status_poll(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=3) as resp:
        return json.load(resp)

def wait_chrome_profile(profile, proc):
    portfile = profile / "DevToolsActivePort"
    deadline = time.monotonic() + 18
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("Isolated Chrome exited early")
        try:
            if portfile.exists():
                port = int(portfile.read_text(encoding="utf-8").splitlines()[0])
                status_poll(port, "/json/version")
                return port
        except (OSError, ValueError, TimeoutError, IndexError):
            pass
        time.sleep(.13)
    raise TimeoutError("Dedicated Chrome CDP port unavailable")

def record():
    if sys.platform != "win32":
        raise RuntimeError("Windows required")
    if not CHROME.is_file() or not FIXTURE.is_file():
        raise FileNotFoundError("Chrome or local demo fixture missing")
    original_focus = USER32.GetForegroundWindow()
    frames, durations, events = [], [], []
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        with tempfile.TemporaryDirectory(prefix="wsb-real-window-") as temp:
            runtime = Path(temp) / "session"
            profile = runtime / "profile"
            runtime.mkdir()
            # Separate profile ensures no personal Chrome tabs, extensions, or
            # user browsing history can appear in this recording.
            args = [str(CHROME), "--no-first-run", "--no-default-browser-check",
                    "--disable-extensions", "--disable-background-networking", "--disable-translate", "--lang=en-US",
                    "--remote-debugging-address=127.0.0.1",
                    "--remote-debugging-port=0", "--remote-allow-origins=http://localhost",
                    f"--user-data-dir={profile}", "--new-window",
                    "--window-position=90,70", "--window-size=1250,810",
                    url + "/"]
            process = None
            port = None
            try:
                process = subprocess.Popen(
                    args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, close_fds=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                port = wait_chrome_profile(profile, process)
                hwnd = find_window(process.pid)
                lane = BrowserLane(runtime=runtime)
                _atomic_json(lane.session, {
                    "pid": process.pid, "created": process_identity(process.pid),
                    "port": port, "profile": str(profile),
                })
                pages = status_poll(port, "/json/list")
                initial = next(p for p in pages if p.get("type") == "page"
                               and p.get("url", "").startswith(url))
                first = initial["id"]
                _atomic_json(lane.owned, [first])
                USER32.SetWindowPos(hwnd, 0, 80, 65, 1240, 795, 0x0010 | 0x0004)

                def snap(name, length=850, current=first):
                    # Real DOM state is asserted before capturing OS pixels.
                    state = lane.read(current)
                    if not state.get("title", "").startswith("Semantic Bridge"):
                        raise RuntimeError("Page identity verification failed")
                    view = screenshot(hwnd)
                    frames.append(decorate(view, name, len(lane.list())))
                    durations.append(length)
                    events.append(name)

                # Wait until the page has painted, not only until DOMContentLoaded.
                until = time.monotonic() + 7
                while "Example task board" not in lane.read(first).get("text", ""):
                    if time.monotonic() > until:
                        raise TimeoutError("Demo fixture did not load")
                    time.sleep(.12)
                time.sleep(.6)
                snap("01   Dedicated Chrome window opened", 1200)

                for step, value in enumerate(("Review", "Review accessibility", "Review accessibility state"), 2):
                    assert lane.fill(first, "#taskName", value)["verified"]
                    snap(f"0{step}   Browser Lane fills the input field", 680)

                assert lane.click(first, "#createTask")["invoked"]
                assert "Created: Review accessibility state" in lane.read(first)["text"]
                snap("05   Real button click and DOM result", 1150)

                assert lane.click(first, "#verify")["invoked"]
                assert "State verified" in lane.read(first)["text"]
                snap("06   Verify the updated page state", 1100)

                tab = lane.new(url + "/docs")
                second = tab["tab_id"]
                assert len(lane.list()) == 2
                with lane._page(second) as cdp:
                    cdp.call("Page.bringToFront")
                time.sleep(.35)
                snap("07   A second agent-owned tab appears", 1100, second)

                lane.navigate(second, url + "/verified")
                assert "Owned tab navigation passed" in lane.read(second)["text"]
                snap("08   Navigate the agent-owned tab", 1100, second)

                lane.close(second)
                assert len(lane.list()) == 1
                with lane._page(first) as cdp:
                    cdp.call("Page.bringToFront")
                time.sleep(.25)
                snap("09   Close second tab; first tab intact", 1600)

            finally:
                if process is not None:
                    try:
                        if port is not None:
                            v = status_poll(port, "/json/version")
                            with CDP(v["webSocketDebuggerUrl"]) as cdp:
                                cdp.call("Browser.close")
                    except (OSError, RuntimeError, TimeoutError):
                        pass
                    time.sleep(.3)
                    if process.poll() is None:
                        process.terminate()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
        if original_focus and USER32.IsWindow(original_focus):
            USER32.SetForegroundWindow(original_focus)

    if len(frames) != 9:
        raise RuntimeError("Incomplete demo capture")
    OUTPUT.mkdir(exist_ok=True)
    gif = OUTPUT / "demo-browser-lane.gif"
    still = OUTPUT / "demo-browser-lane.png"
    palette = [f.quantize(colors=90, method=Image.Quantize.MEDIANCUT,
                          dither=Image.Dither.NONE) for f in frames]
    palette[0].save(gif, format="GIF", save_all=True, append_images=palette[1:],
                    duration=durations, loop=0, optimize=True, disposal=2)
    frames[6].save(still, format="PNG", optimize=True)
    return {"gif": str(gif), "gif_bytes": gif.stat().st_size,
            "still": str(still), "frames": len(frames), "events": events,
            "capture": "real isolated visible Chrome OS window"}

if __name__ == "__main__":
    print(json.dumps(record(), indent=2))
