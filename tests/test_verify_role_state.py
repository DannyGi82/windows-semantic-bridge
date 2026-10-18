import pytest
from semantic_actions import SemanticActionPlanner, AmbiguousElement
from test_relay_semantic_actions import adapter

def test_role_based_postcondition_survives_munim_id_reordering():
    p=SemanticActionPlanner()
    t='Window "QA"\n[e19] ComboBox = "Alpha" (expanded)'
    r=p.verify_state_by_role(t,pid=51,revision=5,after_revision=4,
          name="",control_type="ComboBox",expected_state="expanded")
    assert r["verified"] and r["revision"]==5

def test_role_based_lookup_never_selects_ambiguous_unnamed_combo():
    p=SemanticActionPlanner()
    tree='[e1] ComboBox = "One" (expanded)\n[e2] ComboBox = "Two" (expanded)'
    with pytest.raises(AmbiguousElement):
        p.verify_state_by_role(tree,pid=51,revision=5,after_revision=4,
              name="",control_type="ComboBox",expected_state="expanded")

def test_broker_exposes_read_only_role_state_verification():
    dispatcher,backend=adapter()
    backend.revision=5
    backend.tree='[e19] ComboBox = "Alpha" (expanded)'
    out=dispatcher.handle({"op":"verify_role_state","name":"","control_type":"ComboBox",
                           "expected_state":"expanded","revision":4})
    assert out["ok"] and out["result"]["verified"]
