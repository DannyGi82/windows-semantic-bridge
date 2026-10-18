"""Fail-closed Munim action planning and semantic postcondition tests."""
import pytest
from semantic_actions import (
    AmbiguousElement, ElementUnavailable, StaleSemanticState,
    SemanticActionPlanner, UnsupportedSemanticAction,
)
TEXT = '''723 (pid 723), 1 window(s)
── window 0: "LAB-SEMANTIC-ONLY"
Window "LAB-SEMANTIC-ONLY"
  [e1] Edit "Query" = "old"
  [e2] Button "Search"
  [e3] CheckBox "Agree" = "Off"
  [e4] ComboBox "Category" = "Collapsed"
  [e5] TabItem "General"
  [e6] Button "Disabled" (disabled)
  [e7] Button "Duplicate"
  [e8] Button "Duplicate"
'''
def planner():
    return SemanticActionPlanner()

@pytest.mark.parametrize("name,action,kind",[
    ("Query","set_value","Edit"),
    ("Search","invoke","Button"),
    ("Agree","toggle","CheckBox"),
    ("Category","expand","ComboBox"),
    ("Category","collapse","ComboBox"),
    ("General","select","TabItem"),
])
def test_plans_exact_semantic_pattern_without_coordinates(name,action,kind):
    r=planner().prepare(TEXT,pid=723,revision=11,expected_revision=11,name=name,action=action)
    assert r["pid"]==723 and r["revision"]==11
    assert r["target"]=={"name":name,"control_type":kind,"munim_id":r["target"]["munim_id"]}
    assert "loc" not in str(r) and r["action"]==action
    assert r["executor"]=="Windows_MCP.Invoke"
    assert r["requires_visualguard"] is True

@pytest.mark.parametrize("name,action",[
    ("Duplicate","invoke"),("Nonexistent","invoke")
])
def test_ambiguous_or_missing_target_fail_closed(name,action):
    with pytest.raises((AmbiguousElement,ElementUnavailable)):
        planner().prepare(TEXT,pid=723,revision=11,expected_revision=11,name=name,action=action)

def test_rejects_stale_revision():
    with pytest.raises(StaleSemanticState):
        planner().prepare(TEXT,pid=723,revision=12,expected_revision=11,name="Search",action="invoke")

@pytest.mark.parametrize("action",["type","press_key","click","powershell","shell","set_value"])
def test_rejects_unsupported_button_action(action):
    with pytest.raises(UnsupportedSemanticAction):
        planner().prepare(TEXT,pid=723,revision=11,expected_revision=11,name="Search",action=action)

def test_disabled_target_not_actionable():
    with pytest.raises(ElementUnavailable):
        planner().prepare(TEXT,pid=723,revision=11,expected_revision=11,name="Disabled",action="invoke")

@pytest.mark.parametrize("bad",["",None,0,True,"Search\n[e5] Button"])
def test_rejects_invalid_selector(bad):
    with pytest.raises(ValueError):
        planner().prepare(TEXT,pid=723,revision=11,expected_revision=11,name=bad,action="invoke")

def test_verify_exact_postcondition_on_semantic_snapshot():
    newer=TEXT.replace('[e1] Edit "Query" = "old"','[e1] Edit "Query" = "expected"')
    r=planner().verify(newer,pid=723,revision=12,after_revision=11,
                       name="Query",control_type="Edit",expected_value="expected")
    assert r["verified"] is True and r["revision"]==12

def test_verify_rejects_unchanged_revision_and_wrong_value():
    with pytest.raises(StaleSemanticState):
        planner().verify(TEXT,pid=723,revision=11,after_revision=11,
                         name="Query",control_type="Edit",expected_value="old")
    with pytest.raises(AssertionError):
        planner().verify(TEXT,pid=723,revision=12,after_revision=11,
                         name="Query",control_type="Edit",expected_value="expected")

def test_does_not_treat_unlabeled_or_disabled_window_as_valid():
    text='Window "A"\n  [e1] Button ""\n  [e2] Button "Search" (disabled)'
    with pytest.raises(ElementUnavailable):
        planner().prepare(text,pid=723,revision=1,expected_revision=1,name="Search",action="invoke")
