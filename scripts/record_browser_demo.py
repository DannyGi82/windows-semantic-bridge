#!/usr/bin/env python3
"""Record a reproducible GIF of real Browser Lane actions in an isolated Chrome.

Only a disposable local fixture is used. No user Chrome profiles/tabs are read,
no input is injected into the desktop, and no machine screenshots are taken.
Each visual frame is produced by Chrome via Page.captureScreenshot.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
import ctypes
import json
import sys
import tempfile
import threading
import time

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from browser_lane.cdp_lane import BrowserLane  # noqa: E402

FIXTURE = Path(__file__).with_name("demo_fixture.html")
OUTPUT = ROOT / "assets"
OUTPUT_GIF = OUTPUT / "demo-browser-lane.gif"
OUTPUT_PNG = OUTPUT / "demo-browser-lane.png"

class Site(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path not in ("/", "/docs", "/verified"):
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

@contextmanager
def fixture_site():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Site)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

def font(size: int, bold: bool = False):
    name = "segoeuib.ttf" if bold else "segoeui.ttf"
    winfont = Path("C:/Windows/Fonts") / name
    if winfont.exists():
        return ImageFont.truetype(str(winfont), size)
    return ImageFont.load_default()

def chrome_frame(lane: BrowserLane, target: str) -> Image.Image:
    # A Chrome CDP screenshot is a live render of the owned tab, not a mockup.
    with lane._page(target) as cdp:
        cdp.call("Emulation.setDeviceMetricsOverride", {
            "width": 1080, "height": 625, "deviceScaleFactor": 1, "mobile": False,
        })
        cdp.call("Page.enable")
        cdp.call("Page.bringToFront")
        time.sleep(0.16)
        result = cdp.call("Page.captureScreenshot", {
            "format": "png", "fromSurface": True, "captureBeyondViewport": False,
        })
    payload = base64.b64decode(result["data"], validate=True)
    actual = Image.open(BytesIO(payload)).convert("RGB")
    if actual.width < 800 or actual.height < 500:
        raise RuntimeError("Chrome returned incomplete screenshot")
    return actual.resize((960, 556), Image.Resampling.LANCZOS)

def card(screenshot: Image.Image, event: str, tabs: int, focus_unchanged: bool):
    image = Image.new("RGB", (1000, 660), (7, 13, 27))
    d = ImageDraw.Draw(image)
    d.text((24, 16), "CHROME  /  REAL BROWSER LANE CAPTURE", fill=(81, 221, 239), font=font(16, True))
    d.text((24, 47), event, fill=(239, 246, 255), font=font(24, True))
    image.paste(screenshot, (20, 86))
    d.rectangle((19, 85, 980, 642), outline=(44, 91, 112), width=1)
    msg = f"OWNED TABS: {tabs}   |   ISOLATED PROFILE   |   FOCUS UNCHANGED: {'YES' if focus_unchanged else 'NO'}"
    d.text((24, 645), msg, fill=(126, 177, 198), font=font(11))
    return image

def record() -> dict:
    if sys.platform != "win32":
        raise RuntimeError("This demo requires Windows")
    if not FIXTURE.is_file():
        raise FileNotFoundError(FIXTURE)

    initial_focus = ctypes.windll.user32.GetForegroundWindow()
    frames, durations = [], []
    actions = []

    def sample(lane, target, action, pause=850):
        tabs = lane.list()
        focus_ok = ctypes.windll.user32.GetForegroundWindow() == initial_focus
        frame = chrome_frame(lane, target)
        frames.append(card(frame, action, len(tabs), focus_ok))
        durations.append(pause)
        actions.append({"event": action, "tabs": len(tabs), "focus_preserved": focus_ok})
        if not focus_ok:
            raise RuntimeError("Foreground window changed: aborting focus-preserving demo")

    with tempfile.TemporaryDirectory(prefix="wsb-demo-") as temp:
        runtime = Path(temp) / "isolated_chrome"
        with fixture_site() as url:
            lane = BrowserLane(runtime=runtime)
            launched = False
            try:
                start = lane.start()
                launched = True
                if start["already_running"]:
                    raise RuntimeError("Unexpected existing Chrome session")
                first = lane.new(url + "/")
                owned = first["tab_id"]
                current = lane.read(owned)
                assert current["url"].startswith(url) and "Example task board" in current["text"]
                sample(lane, owned, "01 / Start isolated Chrome profile", 1350)

                for i, val in enumerate(("Review", "Review accessibility", "Review accessibility state")):
                    result = lane.fill(owned, "#taskName", val)
                    assert result["verified"]
                    sample(lane, owned, f"0{i+2} / Fill form using Browser Lane", 680)

                result = lane.click(owned, "#createTask")
                assert result["invoked"]
                current = lane.read(owned)
                assert "Created: Review accessibility state" in current["text"]
                sample(lane, owned, "05 / Invoke button → DOM changes", 1150)

                result = lane.click(owned, "#verify")
                assert result["invoked"]
                current = lane.read(owned)
                assert "State verified" in current["text"]
                sample(lane, owned, "06 / Read back verified state", 1100)

                second = lane.new(url + "/docs")
                other = second["tab_id"]
                assert other != owned and len(lane.list()) == 2
                content = lane.read(other)
                assert "Second browser tab created" in content["text"]
                sample(lane, other, "07 / Open second agent-owned tab", 1150)

                nav = lane.navigate(other, url + "/verified")
                assert nav["tab_id"] == other
                content = lane.read(other)
                assert "Owned tab navigation passed" in content["text"]
                sample(lane, other, "08 / Navigate second tab in background", 1200)

                lane.close(other)
                assert len(lane.list()) == 1
                assert "State verified" in lane.read(owned)["text"]
                sample(lane, owned, "09 / Close owned tab; first tab intact", 1500)

                final_focus = ctypes.windll.user32.GetForegroundWindow()
                if initial_focus != final_focus:
                    raise RuntimeError("Demo unexpectedly changed foreground window")
            finally:
                if launched:
                    lane.shutdown()

    OUTPUT.mkdir(exist_ok=True)
    # Preserve real Chrome frames, decreasing to 80 GIF palette colors.
    indexed = [frame.quantize(colors=80, method=Image.Quantize.MEDIANCUT,
                              dither=Image.Dither.NONE) for frame in frames]
    indexed[0].save(
        OUTPUT_GIF, format="GIF", save_all=True, append_images=indexed[1:],
        duration=durations, loop=0, optimize=True, disposal=2,
    )
    frames[-1].save(OUTPUT_PNG, optimize=True)
    return {
        "gif": str(OUTPUT_GIF),
        "gif_bytes": OUTPUT_GIF.stat().st_size,
        "poster": str(OUTPUT_PNG),
        "frames": len(frames),
        "all_focus_preserved": all(x["focus_preserved"] for x in actions),
        "actions": actions,
    }

if __name__ == "__main__":
    print(json.dumps(record(), indent=2))
