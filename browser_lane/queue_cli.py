"""Send bounded commands to the *installed* MV3 native-host extension.

No Chrome debug port. Operations are applied only to tabs owned by the
extension. If the extension/native host is not connected, fail and clean up.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from browser_lane.native_host import SPOOL,normalize_job,_atomic_write
import re

_UUID_FILENAME=re.compile(r"^[a-f0-9]{32}\.json$")


def purge_abandoned_responses(folder,*,now=None):
    """Discard only old, unclaimed responses left after CLI timeouts."""
    now=time.time() if now is None else now
    for path in list(folder.glob("*.json"))[:200]:
        if not _UUID_FILENAME.fullmatch(path.name):
            continue
        try:
            if now-path.stat().st_mtime>60:
                path.unlink(missing_ok=True)
        except OSError:
            pass


def submit(op,**kwargs):
    pending=SPOOL/"pending"
    done=SPOOL/"done"
    pending.mkdir(parents=True,exist_ok=True)
    done.mkdir(parents=True,exist_ok=True)
    purge_abandoned_responses(done)
    ident=uuid.uuid4().hex
    job={"id":ident,"op":op,"created":time.time(),**kwargs}
    job=normalize_job(job)
    path=pending/(ident+".json")
    result=done/(ident+".json")
    _atomic_write(path,job)
    deadline=time.monotonic()+12
    try:
        while time.monotonic()<deadline:
            if result.is_file():
                data=json.loads(result.read_text(encoding="utf-8"))
                if data.get("id")!=ident:raise RuntimeError("native response mismatch")
                return data
            time.sleep(.1)
        return {"id":ident,"ok":False,"error":"OUTCOME_UNKNOWN_TIMEOUT"}
    finally:
        path.unlink(missing_ok=True)
        result.unlink(missing_ok=True)

def main(argv=None):
    p=argparse.ArgumentParser(description="Semantic Bridge Chrome extension queue")
    sub=p.add_subparsers(dest="op",required=True)
    for op in ("status","list","close_all","park"):sub.add_parser(op)
    open_cmd=sub.add_parser("open");open_cmd.add_argument("url")
    nav=sub.add_parser("navigate");nav.add_argument("tab_id",type=int);nav.add_argument("url")
    read=sub.add_parser("read");read.add_argument("tab_id",type=int)
    close=sub.add_parser("close");close.add_argument("tab_id",type=int)
    fill=sub.add_parser("fill");fill.add_argument("tab_id",type=int);fill.add_argument("selector")
    click=sub.add_parser("click");click.add_argument("tab_id",type=int);click.add_argument("selector")
    args=p.parse_args(argv)
    payload=vars(args).copy()
    op=payload.pop("op")
    try:
        if op=="fill":
            payload["value"]=sys.stdin.read(10001)
        response=submit(op,**payload)
        print(json.dumps(response,ensure_ascii=True))
        return 0 if response.get("ok") else 2
    except (ValueError,OSError,RuntimeError) as exc:
        print(json.dumps({"ok":False,"error":type(exc).__name__,
                         "reason":str(exc)[:160]},ensure_ascii=True))
        return 2
if __name__=="__main__":raise SystemExit(main())