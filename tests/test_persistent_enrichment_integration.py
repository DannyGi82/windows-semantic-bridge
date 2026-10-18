from munim_rpc import MunimClient
from bridge import SemanticBridge

def test_munim_default_reuses_owned_worker_and_merges_states():
    client=MunimClient("not_started")
    try:
        assert client._state_worker is not None
        called=[]
        client._state_worker.collect=lambda pid,wanted=None:(called.append((pid,wanted)) or {
            ("CheckBox","Agree"):"checked"
        })
        client.tool=lambda name,args:{"content":[{"type":"text","text":'[e1] CheckBox "Agree"'}]}
        assert '(checked)' in client.text("511")
        assert '(checked)' in client.text("511")
        assert called==[(511,{("CheckBox","Agree")}),(511,{("CheckBox","Agree")})]
    finally:client.close()

def test_client_closes_owned_state_worker():
    client=MunimClient("not_started")
    closed=[]
    client._state_worker.close=lambda:closed.append(True)
    client.close()
    assert closed==[True]

def test_semantic_bridge_stop_releases_state_sampler():
    class Reader:
        def __init__(self):self.closed=0
        def close_state_worker(self):self.closed+=1
    class Watcher:
        def stop(self):pass
    reader=Reader()
    bridge=SemanticBridge(reader,Watcher())
    bridge.stop()
    assert reader.closed==1