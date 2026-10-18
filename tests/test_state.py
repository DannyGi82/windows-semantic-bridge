import pytest
from state import StateTracker, normalize_line

def test_ephemeral_ids_do_not_make_fake_changes():
    tracker=StateTracker()
    first=tracker.apply('[e1] Button "Save"\n[e2] Text "Hello"')
    second=tracker.apply('[e98] Button "Save"\n[e99] Text "Hello"')
    assert first["revision"]==1
    assert second["revision"]==1
    assert second["added"]==[] and second["removed"]==[]

def test_state_reports_only_new_elements():
    tracker=StateTracker()
    tracker.apply('[e1] Button "Save"')
    changed=tracker.apply('[e7] Button "Save"\n[e8] Text "Changed"')
    assert changed["revision"]==2
    assert any("Changed" in x for x in changed["added"])
    assert changed["removed"]==[]

def test_caps_history_and_prevents_unbounded_deltas():
    tracker=StateTracker(max_changes=2, history_size=2)
    tracker.apply('one')
    result=tracker.apply('two\nthree\nfour\nfive')
    assert len(result["added"])<=2
    assert result["truncated"] is True
    tracker.apply('final')
    assert len(tracker.history)<=2

def test_empty_snapshot_is_error_and_cannot_erase_state():
    tracker=StateTracker()
    tracker.apply('alive')
    with pytest.raises(ValueError):
        tracker.apply('   ')
    assert tracker.current_text == 'alive'

def test_oversized_snapshot_refused_without_mutating_existing_state():
    t=StateTracker()
    t.apply("good")
    with pytest.raises(ValueError, match="large"):
        t.apply("X"*40000)
    assert t.current_text == "good"
    assert t.revision == 1

def test_stale_snapshot_cannot_be_represented_as_current():
    t=StateTracker()
    t.apply("first")
    t.mark_stale("unavailable")
    assert t.stale is True
    with pytest.raises(RuntimeError, match="stale"):
        t.get_current()
    t.apply("restored")
    assert t.get_current() == "restored"

def test_reordered_semantic_items_count_as_changed():
    tracker=StateTracker()
    tracker.apply('[e1] Row "alpha"\n[e2] Row "beta"')
    delta=tracker.apply('[e98] Row "beta"\n[e99] Row "alpha"')
    assert delta["changed"] is True
    assert delta["reordered"] is True
    assert delta["revision"] == 2
