import time
import threading
import pytest
from bridge import SemanticBridge
from observer import PassiveObserver

class EventSource:
    def __init__(self):
        self.items=[]
        self.active=False
    def start(self,pid):self.active=True
    def stop(self):self.active=False
    def drain(self):
        items=self.items[:]
        self.items.clear()
        return items

class FakeMunim:
    def __init__(self):
        self.value='[e1] Text "before"'
        self.calls=0
        self.closed=False
    def text(self,app,depth=3,limit=120):
        self.calls+=1
        return self.value
    def close(self):self.closed=True

def wait_until(predicate, timeout=2):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if predicate():return True
        time.sleep(.02)
    return predicate()

def test_background_observer_refreshes_on_events_without_actions():
    watcher=EventSource()
    rpc=FakeMunim()
    bridge=SemanticBridge(rpc,watcher,reconcile_seconds=300)
    observer=PassiveObserver(bridge,check_interval=.03)
    observer.start(4321)
    try:
        assert wait_until(lambda:bridge.status()["revision"]>=1)
        rpc.value='[e9] Text "after"'
        watcher.items.append({"event":32782})
        assert wait_until(lambda:bridge.status()["revision"]>=2)
        assert [r["revision"] for r in observer.changes_since(0)["changes"]]==[1,2]
        assert observer.status()["events_seen"] >= 1
        assert observer.status()["running"] is True
    finally:
        observer.stop()
    assert observer.status()["running"] is False
    assert watcher.active is False

def test_stop_clears_cached_state_and_thread():
    observer=PassiveObserver(SemanticBridge(FakeMunim(),EventSource()),check_interval=.03)
    observer.start(7654)
    assert wait_until(lambda:observer.status()["revision"]>=1)
    observer.stop()
    assert observer.status()["watching_pid"] is None
    with pytest.raises(PermissionError):observer.changes_since(0)

def test_read_errors_record_only_exception_type_and_do_not_crash_monitor():
    rpc=FakeMunim()
    def fail(*args,**kwargs):
        raise ValueError("sensitive application title should not be logged")
    rpc.text=fail
    observer=PassiveObserver(SemanticBridge(rpc,EventSource()),check_interval=.03)
    observer.start(1234)
    try:
        assert wait_until(lambda:observer.status()["last_error"]=="ValueError")
        assert "sensitive" not in str(observer.status())
    finally: observer.stop()

def test_background_thread_exits_when_watched_pid_is_replaced():
    identity={9101:1}
    rpc=FakeMunim()
    watcher=EventSource()
    bridge=SemanticBridge(rpc,watcher,reconcile_seconds=300,
                          identity_of=lambda pid:identity[pid])
    observer=PassiveObserver(bridge,check_interval=.03)
    observer.start(9101)
    try:
        assert wait_until(lambda:observer.status()["revision"]>=1)
        identity[9101]=2
        assert wait_until(lambda:observer.status()["watching_pid"] is None)
        assert wait_until(lambda:observer.status()["running"] is False)
    finally: observer.stop()

def test_status_exposes_backend_refresh_count_without_screen_content():
    rpc=FakeMunim()
    observer=PassiveObserver(SemanticBridge(rpc,EventSource(),reconcile_seconds=300),
                             check_interval=.03)
    observer.start(9991)
    try:
        assert wait_until(lambda:observer.status().get("refreshes",0)>=1)
        time.sleep(.15)
        stats=observer.status()
        assert stats["refreshes"]==1
        assert stats["last_refresh_ms"]>=0
        assert "before" not in str(stats)
    finally:observer.stop()

def test_stop_closes_owned_munim_client():
    rpc=FakeMunim()
    observer=PassiveObserver(SemanticBridge(rpc,EventSource()),check_interval=.03)
    observer.start(34567)
    assert wait_until(lambda: observer.status()["revision"]>=1)
    observer.stop()
    assert rpc.closed is True
