"""New lab CLI subcommands only build read-only plans and postconditions."""
import json
import io
import sys
import bridge_cli

def test_cli_resolve_exact_name(monkeypatch,capsys):
    calls=[]
    monkeypatch.setattr(bridge_cli,"request",lambda payload:(calls.append(payload) or {"ok":True,"result":{"execution_performed":False}}))
    assert bridge_cli.main(["resolve","LAB-ACTION-INVOKE","invoke","3"])==0
    assert calls==[{"op":"prepare_action","name":"LAB-ACTION-INVOKE","action":"invoke","revision":3}]

def test_cli_resolve_by_munim_id(monkeypatch,capsys):
    calls=[]
    monkeypatch.setattr(bridge_cli,"request",lambda payload:(calls.append(payload) or {"ok":True,"result":{"execution_performed":False}}))
    assert bridge_cli.main(["resolve-id","e2","set_value","4"])==0
    assert calls==[{"op":"prepare_element","element_id":"e2","action":"set_value","revision":4}]

def test_cli_verify_reads_expected_value_from_stdin_not_argv(monkeypatch,capsys):
    calls=[]
    monkeypatch.setattr(bridge_cli,"request",lambda payload:(calls.append(payload) or {"ok":True,"result":{"verified":True}}))
    monkeypatch.setattr(sys,"stdin",io.StringIO("LAB-AFTER"))
    assert bridge_cli.main(["verify-id","e1","Edit","7"])==0
    assert calls==[{"op":"verify_element","element_id":"e1",
                    "control_type":"Edit","revision":7,"expected_value":"LAB-AFTER"}]

def test_cli_verify_rejects_large_stdin_without_sending(monkeypatch,capsys):
    monkeypatch.setattr(sys,"stdin",io.StringIO("a"*3000))
    monkeypatch.setattr(bridge_cli,"request",lambda payload:(_ for _ in ()).throw(AssertionError("unsafe relay call")))
    assert bridge_cli.main(["verify","Query","Edit","3"])!=0
def test_cli_verify_toggle_and_combobox_state(monkeypatch):
    calls=[]
    monkeypatch.setattr(bridge_cli,"request",lambda payload:(calls.append(payload) or {"ok":True,"result":{"verified":True}}))
    assert bridge_cli.main(["verify-state","e4","checked","3"])==0
    assert bridge_cli.main(["verify-role-state","","ComboBox","collapsed","4"])==0
    assert calls==[
       {"op":"verify_state","element_id":"e4","expected_state":"checked","revision":3},
       {"op":"verify_role_state","name":"","control_type":"ComboBox",
        "expected_state":"collapsed","revision":4},
    ]
