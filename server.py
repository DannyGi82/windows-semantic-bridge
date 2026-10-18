"""Standalone LAB ONLY MCP server. No input actions, network listener or autostart."""
from __future__ import annotations

import atexit
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP, Image

from munim_rpc import MunimClient
from events import WindowsEventWatcher, foreground_pid
from bridge import SemanticBridge
from observer import PassiveObserver
from process_identity import process_identity

EXE = Path(os.environ.get("SEMANTIC_BRIDGE_MUNIM_EXE", str(Path(__file__).resolve().parent / "external" / "munim-computer-use.exe")))
mcp = FastMCP("semantic-bridge-lab")
bridge = SemanticBridge(MunimClient(str(EXE)), WindowsEventWatcher(),
                        reconcile_seconds=5, identity_of=process_identity)
observer = PassiveObserver(bridge)
atexit.register(bridge.close)

@mcp.tool()
def lab_status() -> dict:
    """Inspect read-only observer status. No observation starts automatically."""
    return observer.status()

@mcp.tool()
def lab_watch_pid(pid: int) -> dict:
    """Explicitly start read-only continuous semantic observation of a PID."""
    return observer.start(pid)

@mcp.tool()
def lab_watch_foreground() -> dict:
    """Explicitly observe current foreground process, without any GUI input."""
    return observer.start(foreground_pid())

@mcp.tool()
def lab_poll(force: bool = False) -> dict:
    """Reconcile observed WinEvents to a bounded semantic delta on request."""
    return bridge.poll(force)

@mcp.tool()
def lab_delta_since(revision: int) -> dict:
    """Get compact deltas since revision; gap=True requires a new full snapshot."""
    return observer.changes_since(revision)

@mcp.tool()
def lab_snapshot() -> dict:
    """Read the current in-memory semantic snapshot of the selected PID."""
    return bridge.state()

@mcp.tool()
def lab_stop() -> dict:
    """Stop the observer, unsubscribe and discard all sensitive cached state."""
    return observer.stop()

@mcp.tool()
def lab_capture_window() -> Image:
    """Explicit visual fallback; blank/invalid captures rejected, no file writes."""
    data, _ = bridge.capture()
    return Image(data=data, format="jpeg")

def main():
    try:
        mcp.run(transport="stdio")
    finally:
        observer.stop()
        bridge.close()

if __name__ == "__main__":
    main()
