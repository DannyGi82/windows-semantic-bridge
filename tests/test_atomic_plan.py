from test_relay_semantic_actions import adapter

def test_current_id_plan_is_atomic_with_actual_revision():
    d,b=adapter()
    b.revision=19
    result=d.handle({"op":"prepare_current_element","element_id":"e1","action":"set_value"})
    assert result["ok"]
    assert result["result"]["revision"]==19
    assert result["result"]["target"]["munim_id"]=="e1"

def test_current_name_plan_is_atomic_with_actual_revision():
    d,b=adapter()
    b.revision=27
    result=d.handle({"op":"prepare_current_action","name":"Find","action":"invoke"})
    assert result["ok"] and result["result"]["revision"]==27

def test_current_plan_does_not_execute_or_accept_arbitrary_writes():
    d,_=adapter()
    bad=d.handle({"op":"prepare_current_action","name":"Find","action":"invoke","value":"danger"})
    assert bad["error"]=="INVALID_REQUEST"
    bad=d.handle({"op":"prepare_current_element","element_id":"e1","action":"shell"})
    assert not bad["ok"]
