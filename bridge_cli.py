"""Explicit local CLI to a read-only Windows named-pipe Semantic Bridge.

No direct GUI execution, no TCP port and no production service modification.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import msvcrt
import os
import subprocess
import sys
import time

from relay_daemon import (
    SESSION_DIR, SESSION_FILE, _secure_runtime, reclaim_stale_session, request,
)


def _print(value):
    print(json.dumps(value, ensure_ascii=True, separators=(",", ":")))


@contextmanager
def _start_lock():
    """Avoid duplicate broker startup across simultaneous CLI processes."""
    SESSION_DIR.mkdir(exist_ok=True)
    path = SESSION_DIR / ".start.lock"
    with path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError("relay start busy") from None
        try:
            _secure_runtime()
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def _start_once():
    with _start_lock():
        if SESSION_FILE.exists():
            try:
                reclaim_stale_session()
            except (OSError, ValueError, RuntimeError):
                _print({"ok": False, "error": "RELAY_ALREADY_PRESENT"})
                return 2

        flags = (getattr(subprocess, "CREATE_NO_WINDOW", 0)
                 | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        subprocess.Popen(
            [sys.executable, os.path.join(os.path.dirname(__file__), "relay_daemon.py")],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=flags,
            close_fds=True, cwd=os.path.dirname(__file__),
        )
        until = time.monotonic() + 7
        while time.monotonic() < until:
            if SESSION_FILE.exists():
                try:
                    result = request({"op": "status"}, timeout=1)
                    if result.get("ok"):
                        _print({
                            "ok": True,
                            "result": {
                                "started": True,
                                "read_only": True,
                                "watching_pid": result["result"]["watching_pid"],
                            },
                        })
                        return 0
                except (OSError, ValueError, ConnectionError, TimeoutError):
                    pass
            time.sleep(0.1)
        _print({"ok": False, "error": "RELAY_START_FAILED"})
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description="read-only local semantic observer")
    commands = parser.add_subparsers(dest="op", required=True)
    for name in ("start", "status", "snapshot", "stop", "shutdown"):
        commands.add_parser(name)
    watch = commands.add_parser("watch")
    watch.add_argument("pid", type=int)
    delta = commands.add_parser("delta")
    delta.add_argument("revision", type=int)
    for kind in ("resolve","resolve-id"):
        tool = commands.add_parser(kind)
        tool.add_argument("selector")
        tool.add_argument("action", choices=("invoke","set_value","toggle","select","expand","collapse"))
        tool.add_argument("revision", type=int)
    for kind in ("verify","verify-id"):
        tool = commands.add_parser(kind)
        tool.add_argument("selector")
        tool.add_argument("control_type")
        tool.add_argument("revision", type=int)
        # Expected value comes from stdin, never process argv.
    state_parser=commands.add_parser("verify-state")
    state_parser.add_argument("element_id")
    state_parser.add_argument("expected_state")
    state_parser.add_argument("revision",type=int)
    role_parser=commands.add_parser("verify-role-state")
    role_parser.add_argument("name")
    role_parser.add_argument("control_type")
    role_parser.add_argument("expected_state")
    role_parser.add_argument("revision",type=int)
    for kind in ("resolve-current-id","resolve-current-name"):
        tool=commands.add_parser(kind)
        tool.add_argument("selector")
        tool.add_argument("action",choices=("invoke","set_value","toggle","select","expand","collapse"))
    commands.add_parser("map-label")
    args = parser.parse_args(argv)

    try:
        if args.op == "start":
            try:
                return _start_once()
            except RuntimeError as exc:
                error = ("RELAY_START_BUSY" if str(exc) == "relay start busy"
                         else "RELAY_START_FAILED")
                _print({"ok": False, "error": error})
                return 2

        payload = {"op": args.op}
        if args.op == "watch":
            payload["pid"] = args.pid
        if args.op == "delta":
            payload["revision"] = args.revision
        if args.op in ("resolve","resolve-id"):
            payload = {
                "op":"prepare_action" if args.op=="resolve" else "prepare_element",
                "name" if args.op=="resolve" else "element_id":args.selector,
                "action":args.action,"revision":args.revision,
            }
        elif args.op in ("verify","verify-id"):
            value=sys.stdin.read(2049)
            if len(value)>2048:
                _print({"ok":False,"error":"INVALID_REQUEST"})
                return 2
            payload={
                "op":"verify_action" if args.op=="verify" else "verify_element",
                "name" if args.op=="verify" else "element_id":args.selector,
                "control_type":args.control_type,"revision":args.revision,
                "expected_value":value,
            }
        if args.op=="verify-state":
            payload={"op":"verify_state","element_id":args.element_id,
                     "expected_state":args.expected_state,"revision":args.revision}
        elif args.op=="verify-role-state":
            payload={"op":"verify_role_state","name":args.name,
                     "control_type":args.control_type,
                     "expected_state":args.expected_state,"revision":args.revision}
        if args.op in ("resolve-current-id","resolve-current-name"):
            payload={"op":"prepare_current_element" if args.op.endswith("-id") else "prepare_current_action",
                     "element_id" if args.op.endswith("-id") else "name":args.selector,
                     "action":args.action}
        if args.op=="map-label":
            from mcp_label_mapper import resolve_label
            try:
                raw=sys.stdin.read(220000)
                if len(raw)>=220000:raise ValueError("oversized mapper input")
                doc=json.loads(raw)
                if type(doc) is not dict or set(doc)!={"plan","snapshot"}:
                    raise ValueError("invalid mapping envelope")
                resolved=resolve_label(doc["plan"],doc["snapshot"])
                _print({"ok":True,"result":resolved})
                return 0
            except (ValueError,LookupError,TypeError):
                _print({"ok":False,"error":"ELEMENT_UNAVAILABLE"})
                return 2
        result = request(payload)
        _print(result)
        return 0 if result.get("ok") else 2
    except (OSError, ValueError, KeyError, ConnectionError, TimeoutError):
        _print({"ok": False, "error": "RELAY_UNAVAILABLE"})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())