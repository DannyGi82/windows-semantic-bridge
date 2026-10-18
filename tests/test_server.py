from types import SimpleNamespace
import server

def test_mcp_exposes_only_read_methods_and_deltas():
    tools = server.mcp._tool_manager.list_tools()
    names = {tool.name for tool in tools}
    assert "lab_delta_since" in names
    assert {"lab_watch_pid", "lab_status", "lab_snapshot", "lab_stop"} <= names
    assert not ({"click", "type_text", "execute", "powershell", "browser_navigate"} & names)

def test_watch_tool_starts_passive_observation(monkeypatch):
    calls = []
    fake = SimpleNamespace(start=lambda pid: calls.append(pid) or {"watching_pid": pid, "running": True})
    monkeypatch.setattr(server, "observer", fake)
    result = server.lab_watch_pid(4242)
    assert result["running"] is True
    assert calls == [4242]

def test_stop_tool_cleans_passive_observation(monkeypatch):
    calls = []
    fake = SimpleNamespace(stop=lambda: calls.append("stopped") or {"stopped": True, "running": False})
    monkeypatch.setattr(server, "observer", fake)
    assert server.lab_stop()["stopped"] is True
    assert calls == ["stopped"]

def test_server_pins_pid_creation_identity():
    from process_identity import process_identity
    assert server.bridge.identity_of is process_identity
