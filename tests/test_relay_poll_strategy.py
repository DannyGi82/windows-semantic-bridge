from test_relay_semantic_actions import adapter

def test_prepare_action_avoids_unnecessary_forced_uia_rescan():
    d,bridge=adapter()
    calls=[]
    bridge.poll=lambda force=False:(calls.append(force) or {"revision":bridge.revision})
    assert d.handle({"op":"prepare_action","name":"Find","action":"invoke","revision":7})["ok"]
    assert calls==[False]

def test_verify_action_forces_new_sample_after_external_change():
    d,bridge=adapter()
    bridge.revision=8
    bridge.tree='Window "LAB"\n[e1] Edit "Query" = "AFTER"'
    calls=[]
    bridge.poll=lambda force=False:(calls.append(force) or {"revision":bridge.revision})
    assert d.handle({"op":"verify_action","name":"Query","control_type":"Edit",
                     "expected_value":"AFTER","revision":7})["ok"]
    assert calls==[True]
