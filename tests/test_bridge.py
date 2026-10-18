import pytest
from bridge import SemanticBridge

class FakeRpc:
    def __init__(self): self.calls=[]
    def text(self,app,depth=3,limit=120):
        self.calls.append(app)
        return '[e1] Button "Save"'
    def close(self): pass

class FakeWatcher:
    def __init__(self): self.active=False
    def start(self,pid): self.active=True
    def stop(self): self.active=False
    def drain(self): return []

def test_refuses_poll_before_watch():
    bridge=SemanticBridge(FakeRpc(),FakeWatcher())
    with pytest.raises(PermissionError):bridge.poll()

def test_watch_pid_and_refresh_without_extra_calls():
    rpc=FakeRpc()
    bridge=SemanticBridge(rpc,FakeWatcher(),reconcile_seconds=999)
    bridge.watch(1001)
    first=bridge.poll(force=True)
    assert first["revision"]==1
    again=bridge.poll(force=False)
    assert again["unchanged"] is True
    assert rpc.calls == ['1001']

def test_reacts_to_buffer_events():
    rpc=FakeRpc()
    class EventWatcher(FakeWatcher):
        def drain(self): return [{"event":0x800E}]
    bridge=SemanticBridge(rpc,EventWatcher(),reconcile_seconds=999)
    bridge.watch(2002)
    assert bridge.poll()["revision"]==1
    assert bridge.poll()["unchanged"] is True or bridge.poll()["revision"]==1

def test_failed_refresh_invalidates_snapshot_until_success():
    class FailOnce(FakeRpc):
        def __init__(self):
            super().__init__()
            self.fails = False
        def text(self, app, depth=3, limit=120):
            if self.fails:
                raise OSError("broken backend")
            return super().text(app,depth,limit)
    rpc=FailOnce()
    bridge=SemanticBridge(rpc,FakeWatcher())
    bridge.watch(1001)
    bridge.poll(force=True)
    rpc.fails=True
    with pytest.raises(OSError):
        bridge.poll(force=True)
    with pytest.raises(RuntimeError,match="stale"):
        bridge.state()
    rpc.fails=False
    bridge.poll(force=True)
    assert bridge.state()["revision"] == 1

def test_stale_snapshot_is_retried_by_ordinary_poll():
    class Flaky(FakeRpc):
        def __init__(self):
            super().__init__()
            self.fail=False
        def text(self,app,depth=3,limit=120):
            if self.fail:
                raise OSError("unavailable")
            return super().text(app,depth,limit)
    rpc=Flaky()
    bridge=SemanticBridge(rpc,FakeWatcher(),reconcile_seconds=99999)
    bridge.watch(1040)
    bridge.poll(force=True)
    rpc.fail=True
    with pytest.raises(OSError):
        bridge.poll(force=True)
    rpc.fail=False
    result=bridge.poll(force=False)
    assert result["unchanged"] is True
    assert bridge.status()["stale"] is False
    assert rpc.calls==["1040","1040"]

def test_stop_waits_for_inflight_snapshot_and_clears_state():
    import threading
    started=threading.Event()
    release=threading.Event()
    finished=threading.Event()
    class SlowRpc(FakeRpc):
        def text(self,app,depth=3,limit=120):
            started.set()
            if not release.wait(timeout=3):
                raise TimeoutError("test release not set")
            return super().text(app,depth,limit)
    bridge=SemanticBridge(SlowRpc(),FakeWatcher())
    bridge.watch(1901)
    poller=threading.Thread(target=lambda: bridge.poll(force=True),daemon=True)
    poller.start()
    assert started.wait(timeout=2)
    def stop():
        bridge.stop()
        finished.set()
    stopper=threading.Thread(target=stop,daemon=True)
    stopper.start()
    assert not finished.wait(timeout=0.1), "stop must wait for ongoing read"
    release.set()
    poller.join(timeout=3)
    stopper.join(timeout=3)
    assert not poller.is_alive() and not stopper.is_alive()
    assert bridge.status()["watching_pid"] is None
    assert bridge.status()["snapshot_ready"] is False
