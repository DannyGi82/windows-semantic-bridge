"""An exited Windows process must never remain a valid semantic watch target."""
import subprocess
import sys
import pytest
from process_identity import process_identity

def test_exited_process_handle_retained_by_parent_must_be_rejected():
    executable=sys.executable
    p=subprocess.Popen([executable,"-c","import time;time.sleep(.15)"],
                       stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    pid=p.pid
    try:
        initial=process_identity(pid)
        assert isinstance(initial,int) and initial>0
        assert p.wait(timeout=3)==0
        # The parent still holds the Windows process handle, so PID queries
        # can succeed after termination; creation time alone is insufficient.
        with pytest.raises(ProcessLookupError):
            process_identity(pid)
    finally:
        if p.poll() is None:
            p.kill();p.wait(timeout=2)
