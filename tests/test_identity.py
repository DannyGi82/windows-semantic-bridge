import os
import pytest
from bridge import SemanticBridge
from process_identity import process_identity

class FakeWatcher:
    def start(self,pid):pass
    def stop(self):pass
    def drain(self):return []

class FakeRpc:
    def __init__(self):self.calls=0
    def text(self,pid):self.calls+=1;return '[e1] Text "A"'

def test_process_identity_is_stable_for_live_process():
    assert process_identity(os.getpid()) == process_identity(os.getpid())

def test_pid_reused_or_process_changed_stops_observation():
    ident={3001:111}
    rpc=FakeRpc()
    bridge=SemanticBridge(rpc,FakeWatcher(),identity_of=lambda pid:ident[pid])
    bridge.watch(3001)
    assert bridge.poll(force=True)["revision"]==1
    ident[3001]=222
    with pytest.raises(RuntimeError,match="identity changed"):
        bridge.poll(force=True)
    assert bridge.status()["watching_pid"] is None
    assert bridge.status()["snapshot_ready"] is False
    assert rpc.calls==1

def test_inaccessible_pid_does_not_start_observation():
    def deny(pid):
        raise ProcessLookupError("not accessible")
    bridge=SemanticBridge(FakeRpc(),FakeWatcher(),identity_of=deny)
    with pytest.raises(ProcessLookupError):
        bridge.watch(5001)
    assert bridge.status()["watching_pid"] is None

def test_pid_identity_is_rechecked_after_semantic_read():
    identity={3002:111}
    class SwitchingRpc(FakeRpc):
        def text(self,pid):
            self.calls+=1
            identity[3002]=222
            return '[e9] Text "wrong new process"'
    rpc=SwitchingRpc()
    bridge=SemanticBridge(rpc,FakeWatcher(),identity_of=lambda pid:identity[pid])
    bridge.watch(3002)
    with pytest.raises(RuntimeError,match="identity changed"):
        bridge.poll(force=True)
    assert bridge.status()["watching_pid"] is None
    assert bridge.status()["snapshot_ready"] is False

def test_pid_identity_is_rechecked_after_screenshot_capture():
    identity={3003:111}
    class SwitchingCapture(FakeRpc):
        def capture(self,pid):
            identity[3003]=222
            return b"hidden-new-process",{"width":100,"height":100}
    bridge=SemanticBridge(SwitchingCapture(),FakeWatcher(),identity_of=lambda pid:identity[pid])
    bridge.watch(3003)
    with pytest.raises(RuntimeError,match="identity changed"):
        bridge.capture()
    assert bridge.status()["watching_pid"] is None
