"""Real Chrome headless tests: only owned CDP pages, no ordinary tabs affected."""
import ctypes
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import threading,time,pytest
from browser_lane.cdp_lane import BrowserLane
class Site(BaseHTTPRequestHandler):
    def do_GET(self):
        body=b"""<html><title>Semantic Bridge Browser Lab</title><body>
           <input id='q' aria-label='Query' value='before'>
           <button id='go' onclick="document.getElementById('out').textContent=document.getElementById('q').value">Submit</button>
           <div id='out'>INITIAL</div><a href='/next'>Next</a>
           </body></html>"""
        self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass

@pytest.fixture
def server():
    s=ThreadingHTTPServer(("127.0.0.1",0),Site)
    t=threading.Thread(target=s.serve_forever,daemon=True);t.start()
    try:yield f"http://127.0.0.1:{s.server_address[1]}"
    finally:s.shutdown();s.server_close();t.join(timeout=3)

def test_background_pages_and_actions_never_steal_foreground(tmp_path,server):
    lane=BrowserLane(runtime=tmp_path/"browser")
    before=ctypes.windll.user32.GetForegroundWindow()
    try:
        launched=lane.start()
        assert not launched["already_running"]
        assert lane.start()["already_running"]
        a=lane.new(server+"/a")
        b=lane.new(server+"/b")
        assert a["background"] and b["background"]
        assert len(lane.list())==2
        read=lane.read(a["tab_id"])
        assert "INITIAL" in read["text"]
        assert "Query" in [f["label"] for f in read["fields"]]
        assert lane.fill(a["tab_id"],"#q","AGENT_ONLY")["verified"]
        assert lane.click(a["tab_id"],"#go")["invoked"]
        assert "AGENT_ONLY" in lane.read(a["tab_id"])["text"]
        assert "INITIAL" in lane.read(b["tab_id"])["text"]
        assert lane.navigate(b["tab_id"],server+"/next")["url"].endswith("/next")
        assert len(lane.list())==2
        with pytest.raises(PermissionError):
            lane.read("ABCDEF12")
        with pytest.raises(ValueError):
            lane.navigate(a["tab_id"],"file:///C:/secret.txt")
        lane.close(b["tab_id"])
        assert len(lane.list())==1
        assert before==ctypes.windll.user32.GetForegroundWindow()
    finally:
        if lane.session.exists():lane.shutdown()
    assert before==ctypes.windll.user32.GetForegroundWindow()
def test_restart_ignores_port_file_from_previous_stopped_browser(tmp_path,server):
    runtime=tmp_path/"restarted"
    profile=runtime/"profile"
    profile.mkdir(parents=True)
    (profile/"DevToolsActivePort").write_text("1\n/devtools/browser/stale",encoding="utf-8")
    lane=BrowserLane(runtime=runtime)
    try:
        out=lane.start()
        assert out["port"]!=1
        page=lane.new(server+"/after-restart")
        assert "INITIAL" in lane.read(page["tab_id"])["text"]
    finally:
        if lane.session.exists():lane.shutdown()
def test_three_successive_restart_cycles_keep_profile_owner_clean(tmp_path,server):
    runtime=tmp_path/"three-cycles"
    for iteration in range(3):
        lane=BrowserLane(runtime=runtime)
        try:
            assert lane.start()["already_running"] is False
            tab=lane.new(server+f"/cycle{iteration}")
            assert "INITIAL" in lane.read(tab["tab_id"])["text"]
        finally:
            if lane.session.exists():lane.shutdown()
        assert not lane.session.exists()
def test_portfile_locked_during_chrome_start_is_retried(tmp_path,server,monkeypatch):
    from pathlib import Path
    original=Path.read_text
    failures=[0]
    def temporarily_locked(path,*args,**kwargs):
        if path.name=="DevToolsActivePort" and "port-locked" in str(path) and failures[0]<2:
            failures[0]+=1
            raise PermissionError("Chrome is still writing DevToolsActivePort")
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,"read_text",temporarily_locked)
    lane=BrowserLane(runtime=tmp_path/"port-locked")
    try:
        assert lane.start()["already_running"] is False
        assert failures[0]==2
        tab=lane.new(server+"/race")
        assert "INITIAL" in lane.read(tab["tab_id"])["text"]
    finally:
        if lane.session.exists():lane.shutdown()
