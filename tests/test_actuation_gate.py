from pathlib import Path
import pytest
from lab_action_gate import LabFixtureGate, UnsafeTarget

class FakeWorld:
    def __init__(self): self.process_id=1001; self.create_id=3333; self.window_pid=1001; self.calls=[]
    def identity(self,pid): return self.create_id
    def hwnd_pid(self,hwnd): return self.window_pid
    def write(self,hwnd,value): self.calls.append((hwnd,value)); return True

def gate(world,guard=None):
    return LabFixtureGate(pid=1001,hwnd=811,
                          identity_at_launch=3333,identity_of=world.identity,
                          owner_pid_of=world.hwnd_pid,
                          guard_check=guard,write=world.write)

def test_rejects_without_guard_before_write():
    w=FakeWorld()
    with pytest.raises(UnsafeTarget,match="authorization"):
        gate(w).set_value("LAB-TEST")
    assert not w.calls

def test_rejects_missing_or_negative_guard_decision():
    w=FakeWorld()
    for decision in (lambda:False,lambda:None):
        with pytest.raises(UnsafeTarget,match="authorization"):
            gate(w,decision).set_value("LAB-TEST")
    assert not w.calls

def test_accepts_only_lab_text_when_guard_allows():
    w=FakeWorld()
    g=gate(w,lambda:True)
    assert g.set_value("LAB-TEST") is True
    assert w.calls==[(811,"LAB-TEST")]
    for s in ("NORMAL", "LAB-"+"x"*100, ""):
        with pytest.raises(UnsafeTarget):
            g.set_value(s)
    assert w.calls==[(811,"LAB-TEST")]

def test_fails_closed_on_recycled_pid_and_wrong_window_owner():
    w=FakeWorld()
    g=gate(w,lambda:True)
    w.create_id=4444
    with pytest.raises(UnsafeTarget,match="identity"):g.set_value("LAB-X")
    w.create_id=3333
    w.window_pid=1999
    with pytest.raises(UnsafeTarget,match="owner"):g.set_value("LAB-X")
    assert not w.calls

def test_rejects_guard_checker_exception_and_checks_identity_after_write():
    w=FakeWorld()
    def broken(): raise RuntimeError("guard disconnected")
    with pytest.raises(UnsafeTarget,match="authorization"):
        gate(w,broken).set_value("LAB-X")
    def switched(hwnd,value):
        w.create_id=4444
        return True
    g=LabFixtureGate(pid=1001,hwnd=811,identity_at_launch=3333,
                     identity_of=w.identity,owner_pid_of=w.hwnd_pid,
                     guard_check=lambda:True,write=switched)
    with pytest.raises(UnsafeTarget,match="identity"):g.set_value("LAB-X")

def test_cancelled_latch_rejects_action_even_with_authorization():
    w=FakeWorld()
    g=LabFixtureGate(pid=1001,hwnd=811,identity_at_launch=3333,
                     identity_of=w.identity,owner_pid_of=w.hwnd_pid,
                     guard_check=lambda:True,cancelled=lambda:True,write=w.write)
    with pytest.raises(UnsafeTarget, match="cancel"):
        g.set_value("LAB-ABORT")
    assert w.calls==[]

def test_cancel_during_write_does_not_claim_success():
    w=FakeWorld()
    latch={"aborted":False}
    def writer(hwnd,value):
        latch["aborted"]=True
        return w.write(hwnd,value)
    g=LabFixtureGate(pid=1001,hwnd=811,identity_at_launch=3333,
                     identity_of=w.identity,owner_pid_of=w.hwnd_pid,
                     guard_check=lambda:True,cancelled=lambda:latch["aborted"],write=writer)
    with pytest.raises(UnsafeTarget, match="cancel"):
        g.set_value("LAB-INFLIGHT")
    assert w.calls==[(811,"LAB-INFLIGHT")]

def test_once_cancelled_always_cancelled_until_new_gate_instance():
    w=FakeWorld()
    state={"cancel": True}
    gate=LabFixtureGate(pid=1001,hwnd=811,identity_at_launch=3333,
                     identity_of=w.identity,owner_pid_of=w.hwnd_pid,
                     guard_check=lambda:True,cancelled=lambda:state["cancel"],write=w.write)
    with pytest.raises(UnsafeTarget,match="cancel"):
        gate.set_value("LAB-1")
    state["cancel"]=False
    with pytest.raises(UnsafeTarget,match="cancel"):
        gate.set_value("LAB-2")
    assert w.calls==[]
