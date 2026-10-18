import pytest
from semantic_actions import SemanticActionPlanner, ElementUnavailable, StaleSemanticState

TREE='''Window "QA"
  [e1] Edit "" = "LAB-OLD"
  [e2] Button "Run"
  [e3] Edit "" = "LAB-OTHER" (disabled)
'''
def test_id_resolution_supports_unnamed_native_uia_controls():
    p=SemanticActionPlanner()
    action=p.prepare_by_id(TREE,pid=11,revision=5,expected_revision=5,
                           element_id="e1",action="set_value")
    assert action["target"]["name"]==""
    assert action["target"]["munim_id"]=="e1"
    assert action["target"]["control_type"]=="Edit"
    assert action["execution_performed"] is False

def test_id_resolution_rejects_invalid_or_absent_id():
    p=SemanticActionPlanner()
    for value in ("e0","e-1","e10000","e1;whoami","anything",None):
        with pytest.raises((ValueError,ElementUnavailable)):
            p.prepare_by_id(TREE,pid=11,revision=5,expected_revision=5,element_id=value,action="set_value")

def test_disabled_and_changed_id_fail_closed():
    p=SemanticActionPlanner()
    with pytest.raises(ElementUnavailable):
        p.prepare_by_id(TREE,pid=11,revision=5,expected_revision=5,element_id="e3",action="set_value")
    with pytest.raises(StaleSemanticState):
        p.prepare_by_id(TREE,pid=11,revision=6,expected_revision=5,element_id="e1",action="set_value")

def test_verify_id_observes_changed_state():
    p=SemanticActionPlanner()
    next_tree=TREE.replace('"LAB-OLD"','"LAB-UPDATED"')
    s=p.verify_by_id(next_tree,pid=11,revision=6,after_revision=5,
                     element_id="e1",control_type="Edit",expected_value="LAB-UPDATED")
    assert s["verified"] is True
def test_actual_munim_unnamed_edit_syntax_without_empty_quoted_name():
    actual='3548 (pid 3548), 1 window(s)\n\n[e1] Text "LAB-SEMANTIC-CONTROL-TEST"\n  [e2] Edit = "LAB-SEMANTIC-BEFORE"'
    r=SemanticActionPlanner().prepare_by_id(actual,pid=3548,revision=1,
                     expected_revision=1,element_id="e2",action="set_value")
    assert r["target"]=={"munim_id":"e2","name":"","control_type":"Edit"}
