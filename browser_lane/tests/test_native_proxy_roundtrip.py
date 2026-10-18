"""Real compiled Windows .exe native host proxy and stdio framed queue E2E."""
import os,subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import pytest
from browser_lane.native_host import read_message,frame_message
import browser_lane.queue_cli as queue_cli

ROOT=Path(__file__).resolve().parents[1]
import sys
PY=Path(sys.executable)

@pytest.mark.parametrize("mode",["direct_python","proxy_exe"])
def test_native_proxy_stdio_queue_command_and_response(tmp_path,monkeypatch,mode):
    exe=tmp_path/"native_host_proxy.exe"
    if not (ROOT/"native_host_proxy.exe").is_file():
        pytest.skip("NativeMessaging proxy must be compiled locally; binary is not distributed")
    shutil.copy2(ROOT/"native_host_proxy.exe",exe)
    (tmp_path/"native_host_paths.txt").write_text(
       str(PY)+"\n"+str(ROOT/"native_host.py")+"\n",encoding="utf-8")
    spool=tmp_path/"spool"
    env=os.environ.copy()
    env["SEMANTIC_BRIDGE_NATIVE_SPOOL"]=str(spool)
    monkeypatch.setattr(queue_cli,"SPOOL",spool)
    command=[str(PY),"-u",str(ROOT/"native_host.py")] if mode=="direct_python" else [str(exe)]
    p=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        hello=read_message(p.stdout)
        assert hello=={"type":"native_ready","version":1}
        with ThreadPoolExecutor(max_workers=1) as pool:
            task=pool.submit(queue_cli.submit,"status")
            job=read_message(p.stdout)
            assert job["type"]=="command" and job["op"]=="status"
            p.stdin.write(frame_message({"id":job["id"],"ok":True,
                    "result":{"connected":True,"group_id":7}}))
            p.stdin.flush()
            import time
            time.sleep(1.5)
            print("DIAG_MODE",mode,"DONE_FILES",list((spool/"done").glob("*.json")),flush=True)
            print("DIAG_ALIVE",p.poll() is None,flush=True)
            finished=task.result(timeout=14)
            print("DIAG_RESULT",finished,flush=True)
        assert finished["ok"] and finished["result"]["group_id"]==7
        assert not list((spool/"done").glob("*.json"))
    finally:
        p.stdin.close()
        try:p.wait(timeout=4)
        except subprocess.TimeoutExpired:
            p.kill();p.wait(timeout=4)
        p.stdout.close()
        p.stderr.close()