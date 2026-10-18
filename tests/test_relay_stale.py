import base64
import json
from pathlib import Path
import pytest
import relay_daemon as rd
from process_identity import ProcessUnavailableError

def session_file(monkeypatch,tmp_path,pid=6543,created=112233):
    f=tmp_path/"session.json"
    f.write_text(json.dumps({"schema":1,"pipe":r"\\.\pipe\semantic-bridge-testabc",
          "auth":base64.b64encode(b"x"*32).decode(),"pid":pid,
          "process_created_filetime":created}),encoding="utf-8")
    monkeypatch.setattr(rd,"SESSION_FILE",f)
    return f

def test_reclaims_confirmed_dead_pid(monkeypatch,tmp_path):
    f=session_file(monkeypatch,tmp_path)
    def missing(pid):raise ProcessUnavailableError()
    monkeypatch.setattr(rd,"process_identity",missing)
    assert rd.reclaim_stale_session() is True
    assert not f.exists()

def test_refuses_to_replace_live_matching_pid(monkeypatch,tmp_path):
    f=session_file(monkeypatch,tmp_path)
    monkeypatch.setattr(rd,"process_identity",lambda pid:112233)
    with pytest.raises(RuntimeError,match="active"):
        rd.reclaim_stale_session()
    assert f.exists()

def test_reclaims_recycled_pid_only_with_creation_identity(monkeypatch,tmp_path):
    f=session_file(monkeypatch,tmp_path)
    monkeypatch.setattr(rd,"process_identity",lambda pid:999988)
    assert rd.reclaim_stale_session()
    assert not f.exists()

def test_refuses_corrupted_metadata(monkeypatch,tmp_path):
    f=tmp_path/"session.json"
    f.write_text('{"pid":42}',encoding="utf-8")
    monkeypatch.setattr(rd,"SESSION_FILE",f)
    with pytest.raises((ValueError,RuntimeError)):
        rd.reclaim_stale_session()
    assert f.exists()

def test_refuses_legacy_metadata_when_pid_is_live(monkeypatch,tmp_path):
    f=session_file(monkeypatch,tmp_path)
    data=json.loads(f.read_text());del data["process_created_filetime"]
    f.write_text(json.dumps(data))
    monkeypatch.setattr(rd,"process_identity",lambda pid:999988)
    with pytest.raises(RuntimeError,match="active"):
        rd.reclaim_stale_session()
    assert f.exists()
def test_refuses_uncertain_process_lookup_error(monkeypatch,tmp_path):
    f=session_file(monkeypatch,tmp_path)
    def inaccessible(pid):raise ProcessLookupError("query denied or unknown")
    monkeypatch.setattr(rd,"process_identity",inaccessible)
    with pytest.raises(ProcessLookupError):
        rd.reclaim_stale_session()
    assert f.exists()
