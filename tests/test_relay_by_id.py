from test_relay_semantic_actions import adapter

def test_lab_relay_prepares_unnamed_munim_element_safely():
    d,b=adapter()
    b.tree='Window "QA"\n [e1] Edit "" = "before"'
    out=d.handle({"op":"prepare_element","element_id":"e1","action":"set_value","revision":7})
    assert out["ok"] and out["result"]["target"]["munim_id"]=="e1"
    assert out["result"]["execution_performed"] is False

def test_lab_relay_verifies_munim_element_state():
    d,b=adapter()
    b.revision=8
    b.tree='Window "QA"\n [e1] Edit "" = "after"'
    out=d.handle({"op":"verify_element","element_id":"e1","control_type":"Edit",
                  "revision":7,"expected_value":"after"})
    assert out["ok"] and out["result"]["verified"] is True

def test_action_request_never_executes_host_operation():
    d,b=adapter()
    assert d.handle({"op":"set_value","element_id":"e1","value":"something"})["error"]=="OPERATION_DENIED"
    assert d.handle({"op":"prepare_element","element_id":"e1","action":"set_value",
                     "revision":7,"value":"secret"})["error"]=="INVALID_REQUEST"
