"""Isolated headless Chrome CDP lane; never attaches to a user's Chrome."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import websocket

from browser_lane.protocol import normalize_url, validate_selector, validate_target_id, validate_value

LAB = Path(__file__).resolve().parents[1]
RUNTIME = LAB / ".browser_lane_runtime"
PROFILE = RUNTIME / "profile"
SESSION = RUNTIME / "session.json"
OWNED = RUNTIME / "owned.json"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
MAX_TEXT = 12000

def _atomic_json(path: Path, data):
    tmp=path.with_name(path.name+".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=True),encoding="utf-8")
    os.replace(tmp,path)

def _read_json(path:Path):
    return json.loads(path.read_text(encoding="utf-8"))

def _url(port,path):
    return f"http://127.0.0.1:{port}{path}"

def _version(port):
    with urllib.request.urlopen(_url(port,"/json/version"),timeout=3) as r:
        return json.load(r)

def _targets(port):
    with urllib.request.urlopen(_url(port,"/json/list"),timeout=3) as r:
        return json.load(r)

class CDP:
    def __init__(self, wsurl):
        self.conn=websocket.create_connection(wsurl,timeout=6,origin="http://localhost")
        self.seq=0
    def call(self,method,params=None):
        self.seq+=1
        ident=self.seq
        self.conn.send(json.dumps({"id":ident,"method":method,"params":params or {}},ensure_ascii=False))
        deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            r=json.loads(self.conn.recv())
            if r.get("id")==ident:
                if "error" in r:
                    raise RuntimeError("CDP error: "+str(r["error"])[:320])
                return r.get("result",{})
        raise TimeoutError("CDP request timed out")
    def close(self):
        self.conn.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

class BrowserLane:
    def __init__(self,runtime=RUNTIME):
        self.runtime=Path(runtime)
        self.profile=self.runtime/"profile"
        self.session=self.runtime/"session.json"
        self.owned=self.runtime/"owned.json"
        self._launched_process=None

    def _active(self):
        if not self.session.exists():raise RuntimeError("BROWSER_LANE_NOT_STARTED")
        session=_read_json(self.session)
        # Process identity prevents accidental reuse of stale debug ports/PIDs.
        from browser_lane.process_id import process_identity
        try:
            current=process_identity(int(session["pid"]))
        except (OSError,ValueError,KeyError):
            raise RuntimeError("BROWSER_LANE_STALE_SESSION") from None
        if current!=session.get("created"):
            raise RuntimeError("BROWSER_LANE_STALE_SESSION")
        port=int(session["port"])
        if not 0<port<65536:raise RuntimeError("BROWSER_LANE_INVALID_PORT")
        version=_version(port)
        if not version.get("webSocketDebuggerUrl","").startswith(f"ws://127.0.0.1:{port}/"):
            raise RuntimeError("BROWSER_LANE_ENDPOINT_MISMATCH")
        return port,version

    def start(self):
        if self.session.exists():
            port,version=self._active()
            return {"already_running":True,"port":port,"owned_tabs":len(self.list())}
        if not CHROME.is_file():raise FileNotFoundError(str(CHROME))
        self.runtime.mkdir(parents=True,exist_ok=True)
        # DevToolsActivePort can survive Browser.close. Never use that stale
        # port, and never replace a profile which is still controlled by an
        # unmanaged live browser.
        stale_portfile=self.profile/"DevToolsActivePort"
        if stale_portfile.exists():
            try:
                old_port=int(stale_portfile.read_text(encoding="utf-8").splitlines()[0])
                _version(old_port)
            except (OSError,TimeoutError,ValueError,IndexError):
                stale_portfile.unlink(missing_ok=True)
            else:
                raise RuntimeError("BROWSER_PROFILE_ALREADY_ACTIVE_WITHOUT_SESSION")
        command=[str(CHROME),"--headless=new","--no-first-run",
                 "--no-default-browser-check","--disable-extensions",
                 "--disable-background-networking",
                 "--remote-debugging-address=127.0.0.1",
                 "--remote-debugging-port=0",
                 "--remote-allow-origins=http://localhost",
                 "--user-data-dir="+str(self.profile),
                 "about:blank"]
        process=subprocess.Popen(command,stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0),
            close_fds=True)
        self._launched_process=process
        portfile=self.profile/"DevToolsActivePort"
        try:
            deadline=time.monotonic()+12
            port=None
            while time.monotonic()<deadline:
                if process.poll() is not None:
                    raise RuntimeError("isolated Chrome exited before CDP was ready")
                try:
                    if portfile.exists():
                        raw=portfile.read_text(encoding="utf-8").splitlines()
                        if len(raw)>=2:
                            candidate=int(raw[0])
                            if 0<candidate<65536:
                                port=candidate
                                break
                except (OSError,ValueError,IndexError):
                    # Chrome writes this file non-atomically on Windows, and
                    # may temporarily hold it with an exclusive file lock.
                    pass
                time.sleep(.1)
            if port is None:
                raise TimeoutError("Chrome CDP port did not appear")
            from browser_lane.process_id import process_identity
            identity=process_identity(process.pid)
            # Chrome can write its port file before the listener is ready.
            version=None
            until=time.monotonic()+6
            while time.monotonic()<until:
                try:
                    version=_version(port)
                    break
                except (OSError,TimeoutError):
                    if process.poll() is not None:break
                    time.sleep(.1)
            if version is None:raise TimeoutError("new isolated Chrome CDP unavailable")
            if not version["webSocketDebuggerUrl"].startswith(f"ws://127.0.0.1:{port}/"):
                raise RuntimeError("invalid browser websocket")
            _atomic_json(self.session,{"pid":process.pid,"created":identity,"port":port,
                                       "profile":str(self.profile)})
            _atomic_json(self.owned,[])
            return {"already_running":False,"port":port,"owned_tabs":0}
        except Exception:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=4)
                except subprocess.TimeoutExpired:process.kill()
            try:process.wait(timeout=2)
            except subprocess.TimeoutExpired:pass
            self._launched_process=None
            raise

    def _saved(self):
        tabs=_read_json(self.owned)
        if not isinstance(tabs,list):raise RuntimeError("invalid tab ownership")
        return tabs

    def _browser(self):
        port,v=self._active()
        return port,CDP(v["webSocketDebuggerUrl"])

    def new(self,url):
        url=normalize_url(url)
        port,browser=self._browser()
        with browser:
            result=browser.call("Target.createTarget",
                {"url":"about:blank","background":True,"focus":False})
            target=validate_target_id(result["targetId"])
        owned=self._saved()
        owned.append(target)
        _atomic_json(self.owned,owned)
        try:
            self.navigate(target,url)
        except Exception:
            self.close(target)
            raise
        return {"tab_id":target,"url":url,"background":True}

    def _page(self,target):
        target=validate_target_id(target)
        if target not in self._saved():
            raise PermissionError("tab is not owned by Semantic Bridge")
        port,_=self._active()
        targetinfo=next((x for x in _targets(port)
                  if x.get("id")==target and x.get("type")=="page"),None)
        if targetinfo is None:raise RuntimeError("owned tab no longer exists")
        return CDP(targetinfo["webSocketDebuggerUrl"])

    def navigate(self,target,url):
        url=normalize_url(url)
        with self._page(target) as p:
            result=p.call("Page.navigate",{"url":url})
            if result.get("errorText"):raise RuntimeError(result["errorText"])
            self._ready(p)
        return {"tab_id":target,"url":url}

    def _ready(self,page,timeout=6):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            out=page.call("Runtime.evaluate",{
                "expression":"document.readyState",
                "returnByValue":True})
            if out.get("result",{}).get("value") in ("interactive","complete"):
                return
            time.sleep(.1)
        raise TimeoutError("page load timed out")

    def _eval(self,target,expression):
        with self._page(target) as p:
            r=p.call("Runtime.evaluate",{"expression":expression,
                     "returnByValue":True,"awaitPromise":True})
            if r.get("exceptionDetails"):
                raise RuntimeError("page operation failed")
            return r.get("result",{}).get("value")

    def read(self,target):
        expression="""(() => ({
           title: document.title,
           url: location.href,
           text: (document.body?.innerText || '').slice(0,12000),
           links: Array.from(document.querySelectorAll('a[href]')).slice(0,35)
             .map(a => ({text:(a.innerText||'').slice(0,100),href:a.href})),
           fields: Array.from(document.querySelectorAll('input,textarea,button,select')).slice(0,60)
             .map(e => ({tag:e.tagName.toLowerCase(),id:e.id||'',name:e.name||'',
               type:e.type||'',label:e.getAttribute('aria-label')||'',text:(e.innerText||'').slice(0,80)}))
         }))()"""
        result=self._eval(target,expression)
        if not isinstance(result,dict):raise RuntimeError("document not accessible")
        return {"tab_id":target,**result}

    def fill(self,target,selector,value):
        selector=validate_selector(selector)
        value=validate_value(value)
        js="""(() => {
           const el=document.querySelector(SEL);
           if (!el || !el.isConnected || el.disabled || el.readOnly ||
               !['INPUT','TEXTAREA'].includes(el.tagName)) return {ok:false,reason:'NOT_EDITABLE'};
           const setter=Object.getOwnPropertyDescriptor(
             el.tagName==='INPUT'?HTMLInputElement.prototype:HTMLTextAreaElement.prototype,'value').set;
           setter.call(el,VAL);
           el.dispatchEvent(new Event('input',{bubbles:true}));
           el.dispatchEvent(new Event('change',{bubbles:true}));
           return {ok:el.value===VAL,verifiedValue:el.value.slice(0,200)};
         })()""".replace("SEL",json.dumps(selector)).replace("VAL",json.dumps(value))
        out=self._eval(target,js)
        if not isinstance(out,dict) or out.get("ok") is not True:
            raise RuntimeError("cannot fill selected control")
        return {"tab_id":target,"verified":True,"value":out["verifiedValue"]}

    def click(self,target,selector):
        selector=validate_selector(selector)
        js="""(() => {
            const el=document.querySelector(SEL);
            if (!el || !el.isConnected || el.disabled) return {ok:false};
            el.click();
            return {ok:true};
        })()""".replace("SEL",json.dumps(selector))
        out=self._eval(target,js)
        if not isinstance(out,dict) or out.get("ok") is not True:
            raise RuntimeError("cannot click selected control")
        return {"tab_id":target,"invoked":True}

    def list(self):
        port,_=self._active()
        pages={x.get("id"):x for x in _targets(port) if x.get("type")=="page"}
        return [{"tab_id":t,"title":pages[t].get("title",""),"url":pages[t].get("url","")}
                for t in self._saved() if t in pages]

    def close(self,target):
        target=validate_target_id(target)
        if target not in self._saved():raise PermissionError("tab is not owned")
        _,browser=self._browser()
        with browser:browser.call("Target.closeTarget",{"targetId":target})
        _atomic_json(self.owned,[x for x in self._saved() if x!=target])
        return {"closed":target}

    def shutdown(self):
        port,version=self._active()
        with CDP(version["webSocketDebuggerUrl"]) as b:
            try:b.call("Browser.close")
            except (OSError,RuntimeError,websocket.WebSocketException):pass
        # Chrome owns only the isolated profile; no existing browser sessions.
        # Wait for the exact owned browser PID to exit before allowing
        # another launch on the same profile. No global Chrome shutdown.
        from browser_lane.process_id import process_identity,ProcessUnavailableError
        previous=_read_json(self.session)
        until=time.monotonic()+6
        while time.monotonic()<until:
            try:
                if process_identity(int(previous["pid"])) != previous["created"]:
                    break
            except ProcessUnavailableError:
                break
            time.sleep(.1)
        else:
            raise TimeoutError("isolated Chrome did not terminate; restart refused")
        self.session.unlink(missing_ok=True)
        self.owned.unlink(missing_ok=True)
        if self._launched_process is not None:
            try:
                self._launched_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Terminate only the browser that this Python instance created.
                self._launched_process.terminate()
                self._launched_process.wait(timeout=3)
            self._launched_process=None
        return {"shutdown":True}