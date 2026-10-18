"""Strict relay action plans are read-only; UI writes must happen through Windows MCP."""
from relay_protocol import RelayDispatcher
from test_relay_protocol import FakeObserver

TREE='''Window "LAB"
  [e1] Edit "Query" = "before"
  [e2] Button "Find"
'''

class DummyBridge:
    def __init__(self): self.pid=902;self.revision=7;self.tree=TREE;self.polls=0
    def poll(self,force=False): self.polls+=1;return {"revision":self.revision}
    def state(self):return {"pid":self.pid,"revision":self.revision,"text":self.tree}
    def status(self):return {"watching_pid":self.pid,"revision":self.revision,
                              "snapshot_ready":True,"stale":False}
class FakeObserved(FakeObserver):
    def status(self):return {"watching_pid":902,"read_only":True,"revision":7}
def adapter():
    bridge=DummyBridge()
    return RelayDispatcher(FakeObserved(),bridge),bridge

def test_prepare_returns_plan_but_never_invokes_action():
    gate,backend=adapter()
    r=gate.handle({"op":"prepare_action","name":"Query","action":"set_value","revision":7})
    assert r["ok"]
    assert r["result"]["target"]["munim_id"]=="e1"
    assert r["result"]["execution_performed"] is False
    assert backend.polls==1

def test_prepare_does_not_use_outdated_revision():
    gate,backend=adapter()
    r=gate.handle({"op":"prepare_action","name":"Query","action":"set_value","revision":6})
    assert not r["ok"] and r["error"]=="STALE_STATE"

def test_verify_requires_new_semantic_state_and_expected_value():
    gate,backend=adapter()
    backend.revision=8
    backend.tree=TREE.replace('"before"','"after"')
    r=gate.handle({"op":"verify_action","name":"Query","control_type":"Edit",
                   "revision":7,"expected_value":"after"})
    assert r["ok"] and r["result"]["verified"] is True

def test_verification_failure_is_not_reported_as_success():
    gate,backend=adapter()
    backend.revision=8
    r=gate.handle({"op":"verify_action","name":"Query","control_type":"Edit",
                   "revision":7,"expected_value":"after"})
    assert not r["ok"] and r["error"]=="POSTCONDITION_FAILED"

def test_action_rejects_unselected_target_and_direct_tool_calls():
    gate,backend=adapter()
    backend.pid=None
    assert not gate.handle({"op":"prepare_action","name":"Query","action":"set_value","revision":7})["ok"]
    for op in ("invoke","set_value","click","type","press_key","screenshot"):
        assert gate.handle({"op":op})["error"]=="OPERATION_DENIED"

def test_rejects_unknown_or_extra_parameters_on_prepare_and_verify():
    gate,_=adapter()
    assert gate.handle({"op":"prepare_action","name":"Find","action":"invoke","revision":7,"shell":"yes"})["error"]=="INVALID_REQUEST"
    assert gate.handle({"op":"verify_action","name":"Query","control_type":"Edit","revision":7,
                        "expected_value":"after","pid":902})["error"]=="INVALID_REQUEST"

def test_denies_stale_or_unavailable_snapshot():
    gate,bridge=adapter()
    bridge.status=lambda:{"watching_pid":902,"snapshot_ready":False,"stale":True}
    assert gate.handle({"op":"prepare_action","name":"Find","action":"invoke","revision":7})["error"]=="STALE_STATE"
