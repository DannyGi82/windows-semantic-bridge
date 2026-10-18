from munim_rpc import MunimClient

def test_stateful_snapshot_is_enriched_after_munim_read():
    called=[]
    def enrich(tree,pid):
        called.append(pid)
        return tree+" (checked)"
    client=MunimClient("unlaunched",state_enricher=enrich)
    client.tool=lambda name,args:{"content":[{"type":"text","text":'[e1] CheckBox "Agree"'}]}
    assert client.text("304").endswith("(checked)")
    assert called==[304]

def test_plain_text_remains_compatible_with_decorated_state_sampler():
    client=MunimClient("unlaunched",state_enricher=lambda tree,pid:tree)
    client.tool=lambda name,args:{"content":[{"type":"text","text":'[e1] Edit = "Value"'}]}
    assert 'Value' in client.text("304")
