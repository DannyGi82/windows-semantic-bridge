"""Bounded persistent read-only UIA worker: process lifetime and failure gates."""
import sys
import time
import pytest
from uia_state_worker import StateWorker

WORKER = (
    "import sys,json;"
    "[(print(json.dumps([{'kind':'CheckBox','name':'Agree','state':'checked'}]),flush=True)) "
    "for line in sys.stdin]"
)

def test_reuses_single_worker_for_two_fresh_calls():
    w=StateWorker(command=[sys.executable,"-u","-c",WORKER],timeout=2)
    try:
        a=w.collect(123)
        pid=w.pid
        b=w.collect(123)
        assert pid==w.pid and pid is not None
        assert a==b=={("CheckBox","Agree"):"checked"}
    finally:w.close()
    assert w.pid is None

def test_worker_invalid_pid_fails_before_spawning():
    w=StateWorker(command=[sys.executable,"-u","-c",WORKER],timeout=2)
    for pid in (0,True,"42",-1,None):
        with pytest.raises(ValueError):
            w.collect(pid)
    assert w.pid is None

def test_worker_hang_is_bounded_and_closed():
    w=StateWorker(command=[sys.executable,"-u","-c","import time;time.sleep(8)"],timeout=.25)
    started=time.perf_counter()
    with pytest.raises((TimeoutError,RuntimeError)):
        w.collect(123)
    assert time.perf_counter()-started<2.0
    assert w.pid is None

def test_worker_eof_fails_closed():
    w=StateWorker(command=[sys.executable,"-u","-c","import sys;sys.exit(0)"],timeout=.6)
    with pytest.raises((TimeoutError,RuntimeError)):
        w.collect(123)
    assert w.pid is None

def test_worker_malformed_json_is_not_a_valid_state():
    w=StateWorker(command=[sys.executable,"-u","-c","import sys;print('bad json',flush=True)"],timeout=.6)
    with pytest.raises((ValueError,RuntimeError)):
        w.collect(123)
    assert w.pid is None
def test_worker_supports_expected_semantic_roles():
    w=StateWorker(command=[sys.executable,"-u","-c",WORKER],timeout=2)
    try:
        result=w.collect(321,wanted={("CheckBox","Agree")})
        assert result=={("CheckBox","Agree"):"checked"}
    finally:w.close()

def test_invalid_wanted_filter_refused_before_launch():
    w=StateWorker(command=[sys.executable,"-u","-c",WORKER],timeout=2)
    with pytest.raises(ValueError):
        w.collect(321,wanted={("Button","x")})
    assert w.pid is None
