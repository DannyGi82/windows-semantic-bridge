"""Bounded persistent, read-only COM state collector. No GUI input or listener."""
from __future__ import annotations
import json
import queue
import subprocess
import sys
import threading
from pathlib import Path
from uia_state_enricher import _ALLOWED

class StateWorker:
    def __init__(self, *, command=None, timeout=4):
        self.command=command or [
            sys.executable,"-u",str(Path(__file__).with_name("uia_state_enricher.py")),
            "--stream-native-states"
        ]
        self.timeout=timeout
        self._proc=None
        self._reader=None
        self._responses=None
        self._lock=threading.RLock()

    @property
    def pid(self):
        return self._proc.pid if self._proc is not None and self._proc.poll() is None else None

    def _start(self):
        flags=getattr(subprocess,"CREATE_NO_WINDOW",0)
        self._responses=queue.Queue(maxsize=3)
        self._proc=subprocess.Popen(self.command,stdin=subprocess.PIPE,
           stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
           text=True,encoding="utf-8",errors="replace",bufsize=1,
           creationflags=flags,close_fds=True)
        proc=self._proc
        out=self._responses
        def read():
            try:
                for line in proc.stdout:
                    if len(line)>50000:
                        out.put(("invalid","oversized"),timeout=.2)
                        return
                    out.put(("line",line),timeout=.2)
            except (OSError,queue.Full):
                pass
            finally:
                try:out.put(("eof",None),timeout=.2)
                except queue.Full:pass
        self._reader=threading.Thread(target=read,daemon=True,name="uia-state-read")
        self._reader.start()

    def collect(self,pid,*,wanted=None):
        if type(pid) is not int or not 1<=pid<2**31:
            raise ValueError("invalid PID")
        if wanted is not None:
            if not isinstance(wanted,(set,list,tuple)) or len(wanted)>80:
                raise ValueError("invalid wanted controls")
            for item in wanted:
                if (not isinstance(item,tuple) or len(item)!=2
                    or type(item[0]) is not str or item[0] not in ("CheckBox","RadioButton","ComboBox")
                    or type(item[1]) is not str or len(item[1])>240):
                    raise ValueError("invalid wanted semantic control")
        request=json.dumps({"pid":pid,"wanted":sorted([list(item) for item in wanted]) if wanted is not None else None})
        with self._lock:
            if self.pid is None:
                self.close()
                self._start()
            try:
                self._proc.stdin.write(request+"\n")
                self._proc.stdin.flush()
                try:
                    kind,raw=self._responses.get(timeout=self.timeout)
                except queue.Empty as exc:
                    raise TimeoutError("UI Automation state worker timed out") from exc
                if kind!="line" or len(raw)>50000:
                    raise RuntimeError("UI Automation state worker closed or returned invalid data")
                rows=json.loads(raw)
                if not isinstance(rows,list):
                    raise ValueError("invalid UIA state rows")
                states={}
                rejected=set()
                for row in rows[:140]:
                    if not isinstance(row,dict):
                        continue
                    role=row.get("kind")
                    name=row.get("name")
                    state=row.get("state")
                    if (type(role) is not str or type(name) is not str or len(name)>240
                        or state not in _ALLOWED.get(role,())):
                        continue
                    key=(role,name)
                    if key in rejected:
                        continue
                    if key in states and states[key]!=state:
                        states.pop(key,None)
                        rejected.add(key)
                    else:
                        states[key]=state
                return states
            except (ValueError,RuntimeError,TimeoutError,OSError,BrokenPipeError):
                self.close()
                raise

    def close(self):
        with self._lock:
            proc,self._proc=self._proc,None
            if proc is not None:
                if proc.poll() is None:
                    try:proc.terminate();proc.wait(timeout=.3)
                    except (subprocess.TimeoutExpired,OSError):
                        try:proc.kill();proc.wait(timeout=.7)
                        except (subprocess.TimeoutExpired,OSError):pass
                for stream in (proc.stdin,proc.stdout):
                    try:stream.close()
                    except (OSError,ValueError):pass
            self._reader=None
            self._responses=None