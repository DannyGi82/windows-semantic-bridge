import pytest
from watch_policy import require_same_session

def test_allows_explicit_pid_in_current_windows_session():
    seen=[]
    def lookup(pid):
        seen.append(pid)
        return {101:2,202:2}[pid]
    assert require_same_session(202,current_pid=101,session_of=lookup)==202
    assert seen==[101,202]

def test_rejects_cross_session_target_even_if_process_exists():
    with pytest.raises(PermissionError,match="session"):
        require_same_session(404,current_pid=101,
                             session_of=lambda pid:{101:2,404:0}[pid])

def test_rejects_target_when_windows_session_unavailable():
    def lookup(pid):
        if pid==404:raise OSError(5,"access denied")
        return 2
    with pytest.raises(PermissionError):
        require_same_session(404,current_pid=101,session_of=lookup)

def test_rejects_booleans_strings_and_invalid_pids():
    for value in (True,0,-1,"123",None,2**31):
        with pytest.raises((ValueError,PermissionError)):
            require_same_session(value,current_pid=101,session_of=lambda _:2)

def test_dispatcher_never_starts_target_when_authorizer_refuses():
    from relay_protocol import RelayDispatcher
    from test_relay_protocol import FakeObserver,FakeBridge
    observer=FakeObserver()
    def deny(pid):raise PermissionError("PID belongs to another session")
    gate=RelayDispatcher(observer,FakeBridge(observer),watch_authorizer=deny)
    r=gate.handle({"op":"watch","pid":404})
    assert not r["ok"] and r["error"]=="NO_TARGET"
    assert observer.calls==[]
