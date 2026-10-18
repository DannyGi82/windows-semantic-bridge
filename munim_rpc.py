"""Safe, read-only Munim JSON-RPC stdio process. No installation or shell commands."""
from __future__ import annotations
import base64
import io
import json
import os
import queue
import subprocess
import threading
from pathlib import Path
from PIL import Image, ImageStat

_READ_TOOLS = frozenset({"list_apps", "get_app_state", "list_displays", "screenshot"})

class MunimError(RuntimeError):
    pass

def check_allowed(name: str) -> None:
    if name not in _READ_TOOLS:
        raise PermissionError("untrusted/action tool blocked by lab read-only gate")

def extract_text(result: dict) -> str:
    if result.get("isError"):
        raise MunimError("Munim reported an error: " + " ".join(
            c.get("text", "")[:200] for c in result.get("content", []) if c.get("type") == "text"))
    text = "\n".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
    if not text.strip():
        raise MunimError("empty Munim result")
    return text

def validate_capture(data: str) -> dict:
    try:
        raw = base64.b64decode(data, validate=True)
        if len(raw) > 15_000_000:
            raise MunimError("image exceeds 15MB limit")
        with Image.open(io.BytesIO(raw)) as img:
            img.load()
            w, h = img.size
            if w < 64 or h < 32:
                raise MunimError("invalid screenshot dimensions")
            # A constant black/blank frame is a common remote-session failure.
            sample = img.convert("RGB")
            sample.thumbnail((128, 128))
            if max(ImageStat.Stat(sample).stddev) < 0.8:
                raise MunimError("blank/constant remote-session frame")
        return {"width": w, "height": h, "bytes": len(raw)}
    except MunimError:
        raise
    except Exception as exc:
        raise MunimError("invalid image payload") from exc

class MunimClient:
    def __init__(self, executable: str, timeout: float = 8.0, state_enricher=None):
        self._state_worker=None
        if state_enricher is None:
            from uia_state_enricher import enrich_tree
            from uia_state_worker import StateWorker
            self._state_worker=StateWorker()
            from semantic_actions import elements
            def state_enricher(tree,pid):
                wanted={(item["control_type"],item["name"]) for item in elements(tree)
                        if item["control_type"] in ("CheckBox","RadioButton","ComboBox")}
                return enrich_tree(tree,pid,collector=lambda which:self._state_worker.collect(
                    which,wanted=wanted))
        self._state_enricher=state_enricher
        self.executable = str(Path(executable).resolve())
        self.timeout = timeout
        self._proc = None
        self._lock = threading.Lock()
        self._responses = queue.Queue(maxsize=8)
        self._next_id = 0

    def _open(self):
        if not Path(self.executable).is_file():
            raise MunimError("portable Munim binary missing")
        env = os.environ.copy()
        env["COMPUTER_USE_BROWSER"] = "0"
        env["COMPUTER_USE_REMOTE_CONTROL"] = "0"
        startup = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._responses = queue.Queue(maxsize=8)
        self._proc = subprocess.Popen(
            [self.executable], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
            cwd=str(Path(self.executable).parent), creationflags=startup, env=env, bufsize=1)
        process = self._proc
        responses = self._responses
        def read():
            try:
                for line in process.stdout:
                    try:
                        responses.put(json.loads(line), timeout=1)
                    except (ValueError, queue.Full):
                        break
            finally:
                try: responses.put(None, timeout=0.2)
                except queue.Full: pass
        threading.Thread(target=read, name="munim-rpc-reader", daemon=True).start()
        self._request("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "semantic-bridge-lab", "version": "0.1"}})
        self._proc.stdin.write(json.dumps({"jsonrpc":"2.0","method":"notifications/initialized","params":{}})+"\n")
        self._proc.stdin.flush()

    def _request(self, method: str, params: dict):
        self._next_id += 1
        expected = self._next_id
        self._proc.stdin.write(json.dumps({"jsonrpc":"2.0","id":expected,"method":method,"params":params})+"\n")
        self._proc.stdin.flush()
        try:
            response = self._responses.get(timeout=self.timeout)
        except queue.Empty as exc:
            self.close()
            raise MunimError("RPC timed out; terminated child process") from exc
        if response is None or response.get("id") != expected:
            self.close()
            raise MunimError("invalid/missing RPC response")
        if response.get("error"):
            raise MunimError("Munim RPC error: " + str(response["error"])[:250])
        return response.get("result", {})

    def tool(self, name: str, args: dict):
        check_allowed(name)
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self.close()
                self._open()
            return self._request("tools/call", {"name":name, "arguments":args})

    def text(self, app: str, depth: int = 3, limit: int = 120) -> str:
        if not app or not str(app).strip():
            raise ValueError("target required")
        bounded_depth = min(12, max(1, depth))
        args = {"app": str(app), "max_depth": bounded_depth,
                "max_elements": min(400, max(1, limit)),
                "ocr": "never", "offscreen": False}
        text = extract_text(self.tool("get_app_state", args))
        # Chromium's accessible controls commonly start below depth 3.
        # Retry only when Munim confirms there were no interactive controls;
        # keep the default fast path cheap for ordinary native windows.
        if "no interactive elements found" in text.lower() and bounded_depth < 8:
            args["max_depth"] = 8
            text = extract_text(self.tool("get_app_state", args))
        if "no interactive elements found" in text.lower():
            raise MunimError("semantic controls unavailable; use explicit screenshot fallback")
        try:
            pid=int(app)
        except (ValueError,TypeError):
            return text
        return self._state_enricher(text,pid)

    def capture(self, app: str):
        r=self.tool("screenshot", {"app":str(app),"format":"jpeg","max_width":1200,"quality":55})
        if r.get("isError"):
            raise MunimError("screenshot tool returned error")
        images=[c for c in r.get("content",[]) if c.get("type")=="image"]
        if len(images)!=1:
            raise MunimError("missing screenshot")
        data=images[0].get("data", "")
        meta=validate_capture(data)
        return base64.b64decode(data),meta

    def close_state_worker(self):
        if self._state_worker is not None:
            self._state_worker.close()

    def close(self):
        self.close_state_worker()
        p, self._proc = self._proc, None
        if p:
            try:
                if p.poll() is None:
                    p.terminate()
                    p.wait(timeout=2)
            except Exception:
                try: p.kill()
                except Exception: pass
            for stream in (p.stdin,p.stdout):
                try: stream.close()
                except Exception: pass

    def __enter__(self): return self
    def __exit__(self, *_): self.close()