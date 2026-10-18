from browser_lane.native_host import expired_commands

def test_only_expired_native_commands_are_reaped():
    inflight={
      "a":("read",100.0),
      "b":("click",105.0),
      "c":("status",108.0)
    }
    expired=expired_commands(inflight,now=109.1,deadline=8)
    assert expired==[("a","read")]
    assert len(inflight)==2 and "a" not in inflight

def test_native_timeout_for_unresolved_mutation_stays_unknown():
    inflight={"x":("click",0.0)}
    expired=expired_commands(inflight,now=10,deadline=8)
    assert expired==[("x","click")]
