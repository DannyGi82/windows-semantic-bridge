import pytest
from probe_event_delivery import parse_ready

def test_event_producer_returns_actual_pid_from_ready_message():
    assert parse_ready("READY 12800", launcher_pid=14812)==12800

def test_event_producer_rejects_invalid_pid_message():
    with pytest.raises(ValueError):
        parse_ready("READY", launcher_pid=14812)
