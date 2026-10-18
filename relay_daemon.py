"""Windows named-pipe session for an on-demand, read-only observer.

No TCP listeners, system services, startup tasks, plugin changes or action APIs.
Uses authenticated, bounded JSON frames, NOT pickle-based send()/recv().
"""
from __future__ import annotations
import base64
import csv
import io
import json
import os
import secrets
import subprocess
import sys
import uuid
from multiprocessing.connection import Listener, Client
from multiprocessing import AuthenticationError
from pathlib import Path

from bridge import SemanticBridge
from events import WindowsEventWatcher
from munim_rpc import MunimClient
from observer import PassiveObserver
from process_identity import process_identity, ProcessUnavailableError
from relay_protocol import RelayDispatcher
from watch_policy import require_same_session

ROOT = Path(__file__).resolve().parent
SESSION_DIR = ROOT / ".relay_runtime"
SESSION_FILE = SESSION_DIR / "session.json"
MAX_REQUEST_BYTES = 4096
MAX_RESPONSE_BYTES = 512000

def _secure_runtime():
    if sys.platform != "win32":
        raise RuntimeError("Windows required")
    SESSION_DIR.mkdir(exist_ok=True)
    user = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"],
                          capture_output=True,text=True,timeout=6,check=True)
    row = next(csv.reader(io.StringIO(user.stdout)))
    sid = row[-1].strip()
    if not sid.startswith("S-1-5-"):
        raise RuntimeError("unable to resolve Windows user SID")
    # Restrict this lab-only directory before writing any credential.
    proc = subprocess.run(["icacls", str(SESSION_DIR), "/inheritance:r",
                           "/grant:r", "*" + sid + ":(OI)(CI)F"],
                           capture_output=True,text=True,timeout=7)
    if proc.returncode != 0:
        raise RuntimeError("cannot protect relay runtime directory")
    return sid

def _session_doc(address,secret):
    return {"schema":1,"pipe":address,"auth":base64.b64encode(secret).decode(),
            "pid":os.getpid(), "process_created_filetime":process_identity(os.getpid())}

def load_session():
    s=json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    if s.get("schema") != 1 or not str(s.get("pipe","")).startswith("\\\\.\\pipe\\semantic-bridge-"):
        raise RuntimeError("invalid relay session metadata")
    return s

def reclaim_stale_session():
    """Remove only a proven-dead broker's metadata, never an uncertain/live PID.

    This does not terminate or replace any running process. A recycled PID can
    be distinguished only when the metadata includes creation FILETIME.
    """
    if not SESSION_FILE.exists():
        return False
    raw = SESSION_FILE.read_bytes()
    current = load_session()
    pid = current.get("pid")
    created = current.get("process_created_filetime")
    if type(pid) is not int or not 1 <= pid <= 2**31-1:
        raise ValueError("invalid relay PID")
    if created is not None and (type(created) is not int or created <= 0):
        raise ValueError("invalid relay creation identity")
    try:
        now = process_identity(pid)
    except ProcessUnavailableError:
        now = None
    if now is not None and (created is None or now == created):
        raise RuntimeError("active or unverified relay session exists")
    if SESSION_FILE.read_bytes() != raw:
        raise RuntimeError("relay session metadata changed during check")
    SESSION_FILE.unlink()
    return True


def request(payload, timeout=6):
    data=load_session()
    secret=base64.b64decode(data["auth"],validate=True)
    if len(secret)!=32:raise ValueError("invalid authentication key")
    conn=Client(data["pipe"],family="AF_PIPE",authkey=secret)
    try:
        frame=json.dumps(payload,ensure_ascii=True,separators=(",",":")).encode()
        if len(frame)>MAX_REQUEST_BYTES:raise ValueError("request too large")
        conn.send_bytes(frame)
        if not conn.poll(timeout):raise TimeoutError("relay request timed out")
        reply=conn.recv_bytes(MAX_RESPONSE_BYTES)
        return json.loads(reply)
    finally:conn.close()

def serve():
    _secure_runtime()
    if SESSION_FILE.exists():
        raise RuntimeError("relay session exists; refusing duplicate start")
    pipe=r"\\.\pipe\semantic-bridge-" + uuid.uuid4().hex
    secret=secrets.token_bytes(32)
    listener=Listener(address=pipe,family="AF_PIPE",authkey=secret)
    bridge=None
    try:
        doc=_session_doc(pipe,secret)
        temp=SESSION_DIR / ("session-"+uuid.uuid4().hex+".tmp")
        try:
            with temp.open("x",encoding="utf-8") as h:
                json.dump(doc,h)
            # Atomic no-overwrite publish: at most one daemon owns metadata.
            os.link(temp, SESSION_FILE)
        finally:
            temp.unlink(missing_ok=True)
        exe=Path(os.environ.get("SEMANTIC_BRIDGE_MUNIM_EXE", str(ROOT / "external" / "munim-computer-use.exe")))
        bridge=SemanticBridge(MunimClient(str(exe),timeout=6),
                              WindowsEventWatcher(),reconcile_seconds=5,
                              identity_of=process_identity)
        observer=PassiveObserver(bridge,check_interval=.05)
        dispatcher=RelayDispatcher(observer,bridge,watch_authorizer=require_same_session)
        while not dispatcher.shutdown_requested:
            try:
                conn=listener.accept()
            except (AuthenticationError, EOFError, OSError):
                # Reject invalid clients without tearing down the authorized observer.
                continue
            try:
                if not conn.poll(2.0):
                    # An authenticated but silent client must not starve other requests.
                    continue
                frame=conn.recv_bytes(MAX_REQUEST_BYTES)
                try:
                    data=json.loads(frame.decode("utf-8"))
                    result=dispatcher.handle(data)
                except (UnicodeDecodeError,ValueError):
                    result={"ok":False,"error":"INVALID_REQUEST"}
                response=json.dumps(result,ensure_ascii=True,separators=(",",":")).encode()
                if len(response)>MAX_RESPONSE_BYTES:
                    response=b'{"ok":false,"error":"RESPONSE_TOO_LARGE"}'
                conn.send_bytes(response)
            except (EOFError,OSError):
                pass
            finally:
                conn.close()
    finally:
        if bridge is not None: bridge.close()
        listener.close()
        try:
            if SESSION_FILE.exists() and load_session().get("pid")==os.getpid():
                SESSION_FILE.unlink()
        except (OSError,ValueError):
            pass

if __name__=="__main__":
    serve()