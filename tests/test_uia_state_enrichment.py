"""UIA state enrichment must not invent controls or states."""
import pytest
from uia_state_enricher import merge_states
from semantic_actions import SemanticActionPlanner, StaleSemanticState, ElementUnavailable

TREE='''Window "LAB"
 [e1] CheckBox "LAB-ACTION-TOGGLE"
 [e2] RadioButton "LAB-ACTION-SELECT"
 [e3] ComboBox = "Alpha"
 [e4] Button "LAB-ACTION-INVOKE"
'''
def test_merge_unique_stateful_controls_preserves_munim_id_and_value():
    enriched=merge_states(TREE,{
        ("CheckBox","LAB-ACTION-TOGGLE"):"checked",
        ("RadioButton","LAB-ACTION-SELECT"):"selected",
        ("ComboBox",""):"expanded",
    })
    assert '[e1] CheckBox "LAB-ACTION-TOGGLE" (checked)' in enriched
    assert '[e2] RadioButton "LAB-ACTION-SELECT" (selected)' in enriched
    assert '[e3] ComboBox = "Alpha" (expanded)' in enriched
    assert '[e4] Button "LAB-ACTION-INVOKE"' in enriched

def test_no_state_is_invented_when_provider_has_no_result():
    assert merge_states(TREE,{})==TREE

def test_ambiguous_accessible_name_is_not_annotated():
    tree='[e1] CheckBox "Same"\n[e2] CheckBox "Same"'
    assert merge_states(tree,{("CheckBox","Same"):"checked"})==tree

def test_unauthorized_state_or_invalid_kind_not_rendered():
    assert merge_states(TREE,{("CheckBox","LAB-ACTION-TOGGLE"):"something"})==TREE
    assert merge_states(TREE,{("Button","LAB-ACTION-INVOKE"):"checked"})==TREE

def test_verify_state_requires_fresh_snapshot_and_explicit_state():
    p=SemanticActionPlanner()
    newer=merge_states(TREE,{("CheckBox","LAB-ACTION-TOGGLE"):"checked"})
    r=p.verify_state(newer,pid=45,revision=5,after_revision=4,
                     element_id="e1",expected_state="checked")
    assert r["verified"] is True
    with pytest.raises(StaleSemanticState):
        p.verify_state(newer,pid=45,revision=4,after_revision=4,
                       element_id="e1",expected_state="checked")
    with pytest.raises(AssertionError):
        p.verify_state(newer,pid=45,revision=5,after_revision=4,
                       element_id="e1",expected_state="unchecked")
    with pytest.raises(ElementUnavailable):
        p.verify_state(TREE,pid=45,revision=5,after_revision=4,
                       element_id="e1",expected_state="checked")
