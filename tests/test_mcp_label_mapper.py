import pytest
from mcp_label_mapper import resolve_label, MappingAmbiguous, MappingUnavailable

SNAPSHOT='''Foreground window: "Private" [pid 101]
Open windows (3):
  - "Private" [pid 101] *focused*
  - "LAB" [pid 902]
  - "Unrelated" [pid 903]
Interactive elements: 100
UI tree:
Window: "Private" [pid 101] (focused)
    [1] Edit "Query" (101,101)
    [2] Button "Run" (102,102)
Window: "LAB" [pid 902]
    [92] Edit "" (450,220)
    [93] Button "Run" (500,240)
    [94] CheckBox "Agree" (500,260)
    [95] ComboBox "" (500,290)
Window: "Unrelated" [pid 903]
    [96] Button "Run" (500,240)
'''
def plan(pid=902,kind="Button",name="Run",id="e3"):
    return {"pid":pid,"revision":2,"action":"set_value" if kind=="Edit" else "invoke",
            "target":{"munim_id":id,"control_type":kind,"name":name},
            "executor":"Windows_MCP.Invoke",
            "requires_visualguard":True,"execution_performed":False}

def test_resolves_exact_pid_role_and_accessible_name_without_coordinates():
    result=resolve_label(plan(),SNAPSHOT)
    assert result=={"label":93,"pid":902,"control_type":"Button",
                    "name":"Run","action":"invoke","revision":2,
                    "requires_visualguard":True}

def test_unnamed_edit_matches_by_pid_and_control_type_only_when_unique():
    result=resolve_label(plan(kind="Edit",name="",id="e2"),SNAPSHOT)
    assert result["label"]==92

def test_foreground_window_cannot_steal_another_pid_match():
    with pytest.raises(MappingUnavailable):
        resolve_label(plan(pid=904),SNAPSHOT)

def test_duplicate_controls_of_same_type_and_name_fail_closed():
    dup=SNAPSHOT.replace('    [94] CheckBox "Agree"', '    [94] Button "Run"')
    with pytest.raises(MappingAmbiguous):
        resolve_label(plan(),dup)

def test_unknown_window_scope_and_missing_pid_fail_closed():
    with pytest.raises(MappingUnavailable):
        resolve_label(plan(), 'Window: "LAB"\n  [93] Button "Run" (4,4)')

def test_disabled_control_never_maps():
    x=SNAPSHOT.replace('[93] Button "Run"','[93] Button "Run" (disabled)')
    with pytest.raises(MappingUnavailable):
        resolve_label(plan(),x)

@pytest.mark.parametrize("tamper",[
    {"requires_visualguard":False},{"execution_performed":True},
    {"executor":"PowerShell"},{"pid":True},{"revision":0},
    {"action":"click"},{"target":{"munim_id":"e3","name":"Run","control_type":"Unknown"}},
])
def test_rejects_non_semantic_or_unsafe_plans(tamper):
    p=plan();p.update(tamper)
    with pytest.raises((ValueError,MappingUnavailable)):
        resolve_label(p,SNAPSHOT)

def test_roles_are_strict_especially_for_unnamed_controls():
    with pytest.raises(MappingUnavailable):
        resolve_label(plan(kind="Edit",name="Run"),SNAPSHOT)

def test_does_not_reuse_old_snapshot_when_label_not_present():
    with pytest.raises(MappingUnavailable):
        resolve_label(plan(),SNAPSHOT.replace('[93] Button "Run"','Button "Run"'))

def test_snapshot_id_need_not_equal_munim_id():
    result=resolve_label(plan(id="e25"),SNAPSHOT)
    assert result["label"]==93

def test_rejects_oversized_snapshot():
    with pytest.raises(ValueError):
        resolve_label(plan(),SNAPSHOT+"a"*1000000)