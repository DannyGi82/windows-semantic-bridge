import pytest
from state import StateTracker

def test_clients_can_receive_multiple_deltas_since_revision():
    t=StateTracker()
    t.apply('[e1] Text "A"')
    t.apply('[e2] Text "B"')
    result=t.changes_since(0)
    assert [v["revision"] for v in result["changes"]]==[1,2]
    assert result["revision"]==2
    assert result["gap"] is False

def test_gap_is_reported_when_old_history_evicted():
    t=StateTracker(history_size=2)
    for value in ("alpha","beta","gamma"):
        t.apply(value)
    result=t.changes_since(0)
    assert result["gap"] is True
    assert [v["revision"] for v in result["changes"]]==[2,3]

def test_latest_revision_returns_empty_deltas():
    t=StateTracker()
    t.apply("one")
    assert t.changes_since(1)["changes"]==[]

def test_invalid_revision_fails_closed():
    t=StateTracker()
    t.apply("one")
    with pytest.raises(ValueError):
        t.changes_since(-1)
    with pytest.raises(ValueError):
        t.changes_since(100)
