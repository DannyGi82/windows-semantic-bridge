"""Deterministic Munim-plan -> Windows MCP Snapshot label mapping.

Does not click, type, capture images or use coordinates. Mapping uses exact
process PID, UIA role and accessible name and fails closed on duplicates.
Only a NEW Windows MCP Snapshot from the action callsite is authoritative.
"""
from __future__ import annotations
import re
from semantic_actions import _CAPABILITIES
from semantic_hierarchy import labels_by_ancestry

class MappingUnavailable(LookupError): pass
class MappingAmbiguous(LookupError): pass

_WINDOW = re.compile(r'^Window:\s+"(?:[^"\\]|\\.)*"\s+\[pid (?P<pid>[1-9]\d{0,9})\](?:\s+.*)?$')
_ITEM = re.compile(
    r'^\s+\[(?P<label>\d{1,5})\]\s+'
    r'(?P<kind>[A-Za-z][A-Za-z0-9]*)\s+'
    r'"(?P<name>(?:[^"\\]|\\.)*)"'
    r'(?P<tail>[^\r\n]*)$'
)

def resolve_label(plan: dict, snapshot: str) -> dict:
    if not isinstance(plan,dict):
        raise ValueError("action plan must be a dict")
    pid=plan.get("pid")
    rev=plan.get("revision")
    target=plan.get("target")
    action=plan.get("action")
    if (type(pid) is not int or not 1<=pid<2**31 or type(rev) is not int
        or rev<1 or plan.get("requires_visualguard") is not True
        or plan.get("execution_performed") is not False
        or plan.get("executor")!="Windows_MCP.Invoke"
        or not isinstance(target,dict)):
        raise ValueError("untrusted or invalid action plan")
    kind=target.get("control_type")
    name=target.get("name")
    munim_id=target.get("munim_id")
    if (type(kind) is not str or action not in _CAPABILITIES.get(kind,())
        or type(name) is not str or len(name)>240
        or type(munim_id) is not str or not re.fullmatch(r'e[1-9]\d{0,3}',munim_id)):
        raise ValueError("invalid semantic element or action")
    if not isinstance(snapshot,str) or not 0<len(snapshot)<200000:
        raise ValueError("invalid Snapshot text")
    in_tree=False
    window_pid=None
    candidates=[]
    for line in snapshot.splitlines():
        if line.strip()=="UI tree:":
            in_tree=True
            continue
        if not in_tree:
            continue
        win=_WINDOW.match(line)
        if win:
            window_pid=int(win.group("pid"))
            continue
        item=_ITEM.match(line)
        if item and window_pid==pid and item.group("kind")==kind:
            observed_name=item.group("name").replace(r'\"','"')
            if observed_name!=name:
                continue
            if "disabled" in item.group("tail").lower():
                continue
            candidates.append(int(item.group("label")))
    if target.get("ancestors"):
        candidates=labels_by_ancestry(snapshot,pid,kind,name,target["ancestors"])
    if not candidates:
        raise MappingUnavailable("no matching control in the target process")
    if len(candidates)!=1:
        raise MappingAmbiguous("multiple identical controls; choose a stricter selector")
    return {"label":candidates[0],"pid":pid,"control_type":kind,
            "name":name,"action":action,"revision":rev,
            "requires_visualguard":True}