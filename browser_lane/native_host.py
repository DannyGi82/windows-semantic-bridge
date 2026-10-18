"""Chrome MV3 native messaging host — local-only fixed operation queue.

Only an explicitly installed Semantic Bridge extension can launch this
native host. It never runs shell commands, reads cookies, controls Chrome
outside the extension's owned tab IDs, or forwards arbitrary JavaScript.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import queue
import re
import struct
import sys
import threading
import time

# Chrome launches this script through a .cmd wrapper: package parent may be absent.
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from browser_lane.protocol import normalize_url, validate_selector, validate_value

SPOOL=Path(os.environ.get("SEMANTIC_BRIDGE_NATIVE_SPOOL",
    str(Path(os.environ.get("LOCALAPPDATA",str(Path.home()))) / "SemanticBridgeBrowserLane")))
_VALID_ID=re.compile(r"^[a-f0-9]{32}$")
_ALLOWED=frozenset(("status","open","navigate","read","fill","click","close","list","close_all","park"))
MAX_FRAME=256_000

# Metadata-only native bridge trace; never log URLs, selectors, form values or page text.
_TRACE=SPOOL/"bridge-trace.log"
def _trace(event,ident="",op=""):
    try:
        SPOOL.mkdir(parents=True,exist_ok=True)
        if _TRACE.exists() and _TRACE.stat().st_size>2_000_000:
            _TRACE.unlink()
        with _TRACE.open("a",encoding="utf-8") as out:
            out.write(f"{time.time():.3f} pid={os.getpid()} event={event} id={ident} op={op}\n")
    except OSError:
        pass

def frame_message(value:dict)->bytes:
    b=json.dumps(value,ensure_ascii=False,separators=(",",":")).encode("utf-8")
    if len(b)>MAX_FRAME:raise ValueError("native messaging frame is oversized")
    return struct.pack("<I",len(b))+b

def read_message(source):
    first=source.read(4)
    if not first:return None
    if len(first)!=4:raise ValueError("incomplete frame header")
    length=struct.unpack("<I",first)[0]
    if length<2 or length>MAX_FRAME:raise ValueError("native message length invalid")
    body=source.read(length)
    if len(body)!=length:raise ValueError("truncated native message")
    return json.loads(body.decode("utf-8"))

def normalize_job(job,*,now=None):
    if type(job) is not dict or not {"id","op","created"}.issubset(job):
        raise ValueError("malformed browser command")
    ident,op,created=job["id"],job["op"],job["created"]
    if (type(ident) is not str or not _VALID_ID.fullmatch(ident)
        or type(op) is not str or op not in _ALLOWED
        or type(created) not in (float,int)):
        raise ValueError("invalid browser command")
    t=time.time() if now is None else now
    if not 0<=t-created<=30:raise ValueError("stale browser command")
    allowed={
       "status":{"id","op","created"},
       "list":{"id","op","created"},
       "close_all":{"id","op","created"},
       "park":{"id","op","created"},
       "open":{"id","op","created","url"},
       "navigate":{"id","op","created","url","tab_id"},
       "read":{"id","op","created","tab_id"},
       "fill":{"id","op","created","tab_id","selector","value"},
       "click":{"id","op","created","tab_id","selector"},
       "close":{"id","op","created","tab_id"},
    }[op]
    if set(job)!=allowed:raise ValueError("unrecognized browser command fields")
    if op in ("open","navigate"):normalize_url(job["url"])
    if op in ("navigate","read","fill","click","close"):
        if type(job["tab_id"]) is not int or not 1<=job["tab_id"]<2**31:
            raise ValueError("invalid tab")
    if op in ("fill","click"):validate_selector(job["selector"])
    if op=="fill":validate_value(job["value"])
    return job

def _atomic_write(path:Path,payload):
    temp=path.with_suffix(".writing")
    temp.write_text(json.dumps(payload,ensure_ascii=True),encoding="utf-8")
    os.replace(temp,path)

def expired_commands(inflight,*,now=None,deadline=8):
    """Expire unresolved extension jobs without ever assuming a write failed."""
    now=time.monotonic() if now is None else now
    expired=[]
    for ident,(op,sent_at) in list(inflight.items()):
        if now-sent_at>deadline:
            expired.append((ident,op))
            del inflight[ident]
    return expired


def _recv_worker(events):
    try:
        while True:
            msg=read_message(sys.stdin.buffer)
            if msg is None:break
            events.put(msg)
    except (OSError,ValueError,UnicodeError):
        pass
    events.put({"type":"disconnected"})

def main():
    pending=SPOOL/"pending"
    done=SPOOL/"done"
    pending.mkdir(parents=True,exist_ok=True)
    done.mkdir(parents=True,exist_ok=True)
    events=queue.Queue(maxsize=80)
    threading.Thread(target=_recv_worker,args=(events,),daemon=True).start()
    sys.stdout.buffer.write(frame_message({"type":"native_ready","version":1}))
    sys.stdout.buffer.flush()
    active={}
    _trace("HOST_READY")
    while True:
        try:
            while True:
                event=events.get_nowait()
                if event.get("type")=="disconnected":
                    _trace("DISCONNECTED");return 0
                ident=event.get("id")
                if type(ident) is str and ident in active:
                    active.pop(ident,None)
                    _trace("RESPONSE",ident,"ok" if event.get("ok") is True else "error")
                    result={"id":ident,"ok":event.get("ok") is True,
                            "result":event.get("result") if event.get("ok") is True else None,
                            "error":None if event.get("ok") is True else str(event.get("error","FAILED"))[:160]}
                    _atomic_write(done/(ident+".json"),result)
        except queue.Empty:
            pass
        for ident,op in expired_commands(active):
            _trace("HOST_TIMEOUT",ident,op)
            _atomic_write(done/(ident+".json"),{
                "id":ident,"ok":False,
                "error":"OUTCOME_UNKNOWN_TIMEOUT" if op in (
                    "open","navigate","fill","click","close","close_all")
                    else "BROWSER_READ_TIMEOUT"})
        for path in list(pending.glob("*.json"))[:20]:
            ident=path.stem
            try:
                if not _VALID_ID.fullmatch(ident):
                    path.unlink(missing_ok=True);continue
                if path.stat().st_size>18000:
                    raise ValueError("oversized command")
                job=normalize_job(json.loads(path.read_text(encoding="utf-8")))
                if job["id"]!=ident:
                    raise ValueError("command identity mismatch")
                active[ident]=(job["op"],time.monotonic())
                _trace("FORWARD",ident,job["op"])
                sys.stdout.buffer.write(frame_message({"type":"command",**job}))
                sys.stdout.buffer.flush()
            except (ValueError,OSError,KeyError):
                _atomic_write(done/(ident+".json"),{"id":ident,"ok":False,
                             "error":"INVALID_COMMAND"})
            finally:
                path.unlink(missing_ok=True)
        time.sleep(.12)

if __name__=="__main__":
    raise SystemExit(main())