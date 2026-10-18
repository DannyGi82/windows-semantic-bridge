import pytest
from process_identity import ProcessUnavailableError, classify_open_error

def test_access_denied_does_not_equal_exited_pid():
    with pytest.raises(PermissionError):
        classify_open_error(5)

def test_invalid_pid_error_is_certainly_unavailable():
    with pytest.raises(ProcessUnavailableError):
        classify_open_error(87)

def test_unknown_process_error_fails_closed():
    with pytest.raises(OSError):
        classify_open_error(123456)
