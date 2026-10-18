from uia_state_enricher import enrich_tree

def test_enrich_samples_only_when_semantic_stateful_patterns_present():
    called=[]
    def collector(pid):
        called.append(pid)
        return {("CheckBox","Agree"):"checked"}
    assert enrich_tree('[e1] Button "Click"',501,collector=collector)=='[e1] Button "Click"'
    assert called==[]

def test_enrich_includes_explicit_uia_state_without_changing_munim_ids():
    src='[e5] CheckBox "Agree"'
    out=enrich_tree(src,501,collector=lambda pid:{("CheckBox","Agree"):"checked"})
    assert out=='[e5] CheckBox "Agree" (checked)'

def test_enrichment_error_never_fabricates_success_state():
    src='[e5] CheckBox "Agree"'
    def failure(pid):raise PermissionError("no COM access")
    assert enrich_tree(src,501,collector=failure)==src

def test_bad_pid_is_rejected_before_collecting():
    called=[]
    def collector(pid):
        called.append(pid);return {}
    for pid in (0,-1,True,"501"):
        try:enrich_tree('[e1] CheckBox "Agree"',pid,collector=collector)
        except ValueError:pass
        else:raise AssertionError("invalid PID accepted")
    assert called==[]
