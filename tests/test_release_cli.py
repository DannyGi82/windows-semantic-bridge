import io
import json
import sys
import bridge_cli


def test_prepare_live_id(monkeypatch):
    requests=[]
    monkeypatch.setattr(bridge_cli,"request",lambda x: requests.append(x) or {"ok":True})
    assert bridge_cli.main(["resolve-current-id","e12","invoke"])==0
    assert requests==[{"op":"prepare_current_element","element_id":"e12","action":"invoke"}]


def test_prepare_live_name(monkeypatch):
    requests=[]
    monkeypatch.setattr(bridge_cli,"request",lambda x: requests.append(x) or {"ok":True})
    assert bridge_cli.main(["resolve-current-name","Save","invoke"])==0
    assert requests==[{"op":"prepare_current_action","name":"Save","action":"invoke"}]


def test_label_resolution_accepts_stdin_json(monkeypatch,capsys):
    plan={"pid":902,"revision":1,"action":"invoke","target":{
      "munim_id":"e1","control_type":"Button","name":"Go"
    },"executor":"Windows_MCP.Invoke","requires_visualguard":True,"execution_performed":False}
    snapshot='UI tree:\nWindow: "LAB" [pid 902]\n  [20] Button "Go" (10,10)'
    monkeypatch.setattr(sys,"stdin",io.StringIO(json.dumps({"plan":plan,"snapshot":snapshot})))
    assert bridge_cli.main(["map-label"])==0
    assert json.loads(capsys.readouterr().out)["result"]["label"]==20
