import pytest
from mcp_label_mapper import resolve_label, MappingAmbiguous, MappingUnavailable
from semantic_actions import SemanticActionPlanner

TREE='''Window "Lab"
  Group "Billing"
    [e1] Button "Save"
  Group "Shipping"
    [e2] Button "Save"
'''
MCP='''UI tree:
Window: "Lab" [pid 902]
  Pane "Lab"
    Group "Billing"
      [27] Button "Save" (120,200)
    Group "Shipping"
      [28] Button "Save" (120,500)
'''
def prepare(eid):
    return SemanticActionPlanner().prepare_by_id(
      TREE,pid=902,revision=3,expected_revision=3,element_id=eid,action="invoke")

def test_duplicate_uses_enclosing_accessible_group_identity():
    p=prepare("e2")
    assert p["target"]["ancestors"] == [{"control_type":"Group","name":"Shipping"}]
    assert resolve_label(p,MCP)["label"]==28

def test_other_group_never_selected():
    assert resolve_label(prepare("e1"),MCP)["label"]==27

def test_missing_ancestor_fails_even_when_only_one_candidate():
    m=MCP.replace('Group "Shipping"','Group "OTHER"').replace('    Group "Billing"\n      [27] Button "Save" (120,200)\n','')
    with pytest.raises(MappingUnavailable):
        resolve_label(prepare("e2"),m)

def test_same_parent_duplicate_still_fails_closed():
    t='''Window "Lab"
  Group "Billing"
    [e1] Button "Save"
    [e2] Button "Save"
'''
    p=SemanticActionPlanner().prepare_by_id(t,pid=902,revision=3,expected_revision=3,element_id="e2",action="invoke")
    s='''UI tree:
Window: "Lab" [pid 902]
  Group "Billing"
    [1] Button "Save" (10,10)
    [2] Button "Save" (20,20)
'''
    with pytest.raises(MappingAmbiguous):resolve_label(p,s)

def test_conflicting_context_is_not_silently_ignored():
    p=prepare("e2")
    p["target"]["ancestors"]=[{"control_type":"Group","name":"Private"}]
    with pytest.raises(MappingUnavailable):resolve_label(p,MCP)
