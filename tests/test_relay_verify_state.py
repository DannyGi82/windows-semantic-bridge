from test_relay_semantic_actions import adapter

def test_relay_verifies_checked_state_on_new_revision():
    dispatcher,bridge=adapter()
    bridge.revision=8
    bridge.tree='Window "LAB"\n [e1] CheckBox "Agree" (checked)'
    r=dispatcher.handle({"op":"verify_state","element_id":"e1",
                         "expected_state":"checked","revision":7})
    assert r["ok"] and r["result"]["verified"]

def test_relay_never_infers_state_if_uia_did_not_report_it():
    dispatcher,bridge=adapter()
    bridge.revision=8
    bridge.tree='Window "LAB"\n [e1] CheckBox "Agree"'
    r=dispatcher.handle({"op":"verify_state","element_id":"e1",
                         "expected_state":"checked","revision":7})
    assert not r["ok"]

def test_relay_state_verification_rejects_extra_action_payload():
    d,_=adapter()
    r=d.handle({"op":"verify_state","element_id":"e1","expected_state":"checked",
                "revision":7,"action":"toggle"})
    assert r["error"]=="INVALID_REQUEST"
