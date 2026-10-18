from uia_state_enricher import enrich_tree, filter_owned_hwnds

def test_only_owning_pid_windows_included_even_for_embedded_children():
    owners={10:500,20:501,30:500}
    selected=filter_owned_hwnds([10,20,30],500,owner_of=lambda hwnd:owners[hwnd])
    assert selected==[10,30]

def test_unimplemented_tab_and_list_states_do_not_spawn_worker():
    for tree in ('[e1] TabItem "General"','[e2] ListItem "Entry"'):
        assert enrich_tree(tree,500,collector=lambda pid:(_ for _ in ()).throw(AssertionError("unneeded call")))==tree
