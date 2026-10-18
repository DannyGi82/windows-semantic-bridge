"""Read-only UI Automation state decoration for explicit Munim snapshots.

The enrichment data is separate from Munim's own element IDs. State is
appended only if control type and name are unique within the current snapshot;
no coordinate-based matching or inferred toggle state is permitted.
"""
from collections import Counter
from semantic_actions import elements, _LINE

_ALLOWED={
    "CheckBox":frozenset(("checked","unchecked","mixed")),
    "RadioButton":frozenset(("selected","unselected")),
    "ListItem":frozenset(("selected","unselected")),
    "TabItem":frozenset(("selected","unselected")),
    "ComboBox":frozenset(("expanded","collapsed")),
    "TreeItem":frozenset(("expanded","collapsed")),
}


def merge_states(tree: str, states: dict[tuple[str,str],str]) -> str:
    if not states:
        return tree
    items=elements(tree)
    freq=Counter((x["control_type"],x["name"]) for x in items)
    rendered=[]
    for line in tree.splitlines(keepends=True):
        match=_LINE.match(line.rstrip("\r\n"))
        if not match:
            rendered.append(line);continue
        key=(match.group("kind"),match.group("name") or "")
        state=states.get(key)
        if freq[key]!=1 or state not in _ALLOWED.get(key[0],()):
            rendered.append(line);continue
        newline=line[len(line.rstrip("\r\n")):]
        base=line.rstrip("\r\n")
        # Replace an existing decoration rather than accumulating tokens
        for old in _ALLOWED[key[0]]:
            base=base.replace(f" ({old})","")
        rendered.append(base+f" ({state})"+newline)
    return "".join(rendered)

def enrich_tree(tree: str, pid: int, *, collector=None) -> str:
    """Read only native UIA state, using an isolated bounded subprocess.

    If the UIA provider is missing, return the original tree. Consumers must
    treat a missing state as UNKNOWN, never as false or successful.
    """
    if type(pid) is not int or not 1 <= pid < 2**31:
        raise ValueError("invalid watch PID")
    if not any(kind in tree for kind in ("CheckBox","RadioButton","ComboBox")):
        return tree
    if collector is None:
        collector=collect_states
    try:
        states=collector(pid)
    except Exception:
        return tree
    return merge_states(tree,states)


def filter_owned_hwnds(handles, pid, *, owner_of):
    """Exclude foreign-process HWNDs even if embedded inside an owned parent."""
    return [hwnd for hwnd in handles if owner_of(hwnd)==pid]


def collect_states(pid: int) -> dict:
    import json
    import subprocess
    import sys
    from pathlib import Path
    child=subprocess.run(
        [sys.executable,str(Path(__file__).resolve()),"--read-native-states",str(pid)],
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
        text=True,encoding="utf-8",timeout=4,
        creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0),
        check=False)
    if child.returncode != 0 or len(child.stdout)>50000:
        raise RuntimeError("UIA state collector unavailable")
    rows=json.loads(child.stdout)
    states={}
    for item in rows:
        if (not isinstance(item,dict)
            or not isinstance(item.get("kind"),str)
            or not isinstance(item.get("name"),str)
            or item.get("state") not in _ALLOWED.get(item["kind"],())):
            continue
        key=(item["kind"],item["name"])
        if key in states and states[key]!=item["state"]:
            # Conflicting instances are explicitly ambiguous.
            states.pop(key,None)
        else:
            states[key]=item["state"]
    return states


def _read_native_states(pid: int, wanted=None):
    """Child process: inspect only HWNDs whose owning PID exactly matches."""
    import ctypes
    from ctypes import wintypes
    import sys
    sys.coinit_flags=0
    import comtypes.client
    from comtypes.gen import UIAutomationClient as ui

    user=ctypes.WinDLL("user32",use_last_error=True)
    CB=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    user.EnumWindows.argtypes=[CB,wintypes.LPARAM]
    user.EnumChildWindows.argtypes=[wintypes.HWND,CB,wintypes.LPARAM]
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.IsWindowVisible.argtypes=[wintypes.HWND]
    roots=[]
    def enum_top(hwnd,_):
        owner=wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
        if owner.value==pid and user.IsWindowVisible(hwnd) and len(roots)<5:
            roots.append(hwnd)
        return True
    user.EnumWindows(CB(enum_top),0)
    all_hwnds=list(roots)
    def enum_child(hwnd,_):
        if len(all_hwnds)<120:
            all_hwnds.append(hwnd)
        return len(all_hwnds)<120
    child_cb=CB(enum_child)
    for root in roots:
        user.EnumChildWindows(root,child_cb,0)
    def owning_pid(hwnd):
        owner=wintypes.DWORD()
        if not user.GetWindowThreadProcessId(hwnd,ctypes.byref(owner)):
            return None
        return owner.value
    all_hwnds=filter_owned_hwnds(all_hwnds,pid,owner_of=owning_pid)
    from native_win32_state import read_native_hwnd
    native=[]
    for hwnd in all_hwnds:
        try:
            row=read_native_hwnd(hwnd)
            if row is not None:
                native.append(row)
        except Exception:
            continue
    if wanted is not None:
        matched={(item["kind"],item["name"]) for item in native}
        if set(wanted).issubset(matched):
            return native
    automation=comtypes.client.CreateObject(
        "{ff48dba4-60ef-4201-aa87-54103eef594e}",interface=ui.IUIAutomation)
    role_ids={
        ui.UIA_CheckBoxControlTypeId:("CheckBox",ui.UIA_TogglePatternId,
            ui.IUIAutomationTogglePattern,"CurrentToggleState",{0:"unchecked",1:"checked",2:"mixed"}),
        ui.UIA_RadioButtonControlTypeId:("RadioButton",ui.UIA_SelectionItemPatternId,
            ui.IUIAutomationSelectionItemPattern,"CurrentIsSelected",{0:"unselected",1:"selected"}),
        ui.UIA_ComboBoxControlTypeId:("ComboBox",ui.UIA_ExpandCollapsePatternId,
            ui.IUIAutomationExpandCollapsePattern,"CurrentExpandCollapseState",{0:"collapsed",1:"expanded"}),
    }
    found=list(native)
    known={(item["kind"],item["name"]) for item in native}
    for hwnd in all_hwnds:
        try:
            element=automation.ElementFromHandle(hwnd)
            kind=int(element.CurrentControlType)
            if kind not in role_ids:
                continue
            label=element.CurrentName
            semantic_kind,pid_pattern,interface,prop,names=role_ids[kind]
            if (semantic_kind,label) in known:
                continue
            pattern=element.GetCurrentPattern(pid_pattern).QueryInterface(interface)
            value=names.get(int(getattr(pattern,prop)))
            if value is not None and len(label)<=240:
                found.append({"kind":semantic_kind,"name":label,"state":value})
        except Exception:
            continue
    return found


if __name__=="__main__":
    import json
    import sys
    if len(sys.argv)==2 and sys.argv[1]=="--stream-native-states":
        # Same process (and COM apartment) serves repeated short read-only
        # requests. The parent owns a hard timeout and terminates on failure.
        for line in sys.stdin:
            try:
                if len(line)>24000:
                    raise ValueError("oversized UIA request")
                body=json.loads(line)
                pid=body["pid"]
                if type(pid) is not int or not 1<=pid<2**31:
                    raise ValueError("invalid PID")
                raw_wanted=body.get("wanted")
                wanted=None if raw_wanted is None else set()
                if raw_wanted is not None:
                    if not isinstance(raw_wanted,list) or len(raw_wanted)>80:
                        raise ValueError("invalid target list")
                    for entry in raw_wanted:
                        if (not isinstance(entry,list) or len(entry)!=2
                            or entry[0] not in ("CheckBox","RadioButton","ComboBox")
                            or not isinstance(entry[1],str) or len(entry[1])>240):
                            raise ValueError("invalid target item")
                        wanted.add((entry[0],entry[1]))
                result=_read_native_states(pid,wanted=wanted)
            except Exception:
                result=[]
            print(json.dumps(result,ensure_ascii=True),flush=True)
        raise SystemExit(0)
    if len(sys.argv)==3 and sys.argv[1]=="--read-native-states":
        try:
            pid=int(sys.argv[2])
            if not 1<=pid<2**31:
                raise ValueError("invalid PID")
            output=_read_native_states(pid)
            print(json.dumps(output,ensure_ascii=True))
        except Exception:
            print("[]")
            raise SystemExit(3)