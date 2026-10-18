"""Read-only bounded RPC facade. Tests pin fail-closed behavior."""
from relay_protocol import RelayDispatcher

class FakeObserver:
    def __init__(self):
        self.watched=None
        self.calls=[]
    def status(self):return {"watching_pid":self.watched,"read_only":True,"revision":1}
    def start(self,pid):
        self.watched=pid; self.calls.append(("start",pid))
        return {"watching_pid":pid}
    def changes_since(self,rev):
        self.calls.append(("delta",rev))
        return {"revision":2,"changes":[{"revision":2,"added":["LAB-TEST"]}],"gap":False}
    def stop(self):
        self.watched=None;self.calls.append(("stop",))
        return {"stopped":True}

class FakeBridge:
    def __init__(self,obs):self.obs=obs
    def state(self):
        if self.obs.watched is None:raise PermissionError("hidden secret app title")
        return {"revision":1,"text":"LAB-TEST"}

def dispatcher():
    obs=FakeObserver()
    return RelayDispatcher(obs,FakeBridge(obs)),obs

def test_unknown_action_denied_without_calling_observer():
    d,o=dispatcher()
    for op in ["click","invoke","set_value","powershell","run","__class__"]:
        result=d.handle({"op":op})
        assert result["ok"] is False
        assert result["error"]=="OPERATION_DENIED"
    assert o.calls==[]

def test_status_does_not_implicitly_select_target():
    d,o=dispatcher()
    r=d.handle({"op":"status"})
    assert r["ok"] is True and r["result"]["watching_pid"] is None
    assert o.calls==[]

def test_pid_and_revision_validation_denies_bool_negative_and_extras():
    d,o=dispatcher()
    for pid in [True,-1,0, "123",None]:
        assert d.handle({"op":"watch","pid":pid})["ok"] is False
    for rev in [True,-1,2.5,"0"]:
        assert d.handle({"op":"delta","revision":rev})["ok"] is False
    assert d.handle({"op":"watch","pid":1234,"shell":"powershell"})["ok"] is False
    assert o.calls==[]

def test_watch_then_delta_then_stop_only():
    d,o=dispatcher()
    assert d.handle({"op":"watch","pid":1234})["ok"]
    delta=d.handle({"op":"delta","revision":1})
    assert delta["result"]["changes"][0]["added"]==["LAB-TEST"]
    assert d.handle({"op":"stop"})["result"]["stopped"]
    assert o.calls==[("start",1234),("delta",1),("stop",)]

def test_snapshot_before_watch_is_sanitized():
    d,o=dispatcher()
    result=d.handle({"op":"snapshot"})
    assert result["ok"] is False
    assert "secret" not in str(result)
    assert "Traceback" not in str(result)

def test_oversized_or_non_dict_request_denied():
    d,o=dispatcher()
    assert not d.handle(["status"])["ok"]
    assert not d.handle({"op":"status","value":"x"*2048})["ok"]
