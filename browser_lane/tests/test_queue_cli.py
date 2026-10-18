"""Native queue cannot send arbitrary operations and cleans expired jobs."""
import pytest
from browser_lane.native_host import normalize_job
from browser_lane.queue_cli import submit

def test_spool_will_not_create_unknown_job(tmp_path,monkeypatch):
    import browser_lane.queue_cli as cli
    import browser_lane.native_host as host
    monkeypatch.setattr(cli,"SPOOL",tmp_path)
    monkeypatch.setattr(host,"SPOOL",tmp_path)
    with pytest.raises(ValueError):
        submit("arbitrary_code",script="alert(1)")
    assert not list(tmp_path.rglob("*.json"))

def test_native_queue_fails_when_extension_not_connected(tmp_path,monkeypatch):
    import browser_lane.queue_cli as cli
    monkeypatch.setattr(cli,"SPOOL",tmp_path)
    ticks=iter(range(30))
    start=[0]
    monkeypatch.setattr(cli.time,"monotonic",lambda:next(ticks))
    monkeypatch.setattr(cli.time,"sleep",lambda secs:None)
    result=submit("status")
    assert not result["ok"] and result["error"]=="OUTCOME_UNKNOWN_TIMEOUT"
    assert not list((tmp_path/"pending").glob("*.json"))
def test_purge_late_responses_only_older_than_one_minute(tmp_path):
    import os,time
    from browser_lane.queue_cli import purge_abandoned_responses
    folder=tmp_path/"done"
    folder.mkdir()
    stale=folder/("a"*32+".json")
    fresh=folder/("b"*32+".json")
    unrelated=folder/"other.json"
    for path in (stale,fresh,unrelated):path.write_text("{}")
    ts=time.time()
    os.utime(stale,(ts-120,ts-120))
    os.utime(unrelated,(ts-120,ts-120))
    purge_abandoned_responses(folder,now=ts)
    assert not stale.exists() and fresh.exists() and unrelated.exists()
