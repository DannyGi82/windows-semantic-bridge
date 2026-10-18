"""Accessible hierarchy for disambiguating repeated UIA role/name pairs.

Only explicit control ancestry is accepted. Never match based on pixel position
or the arbitrary ordering of duplicate sibling controls.
"""
import re

_PARENT_ROLES=frozenset({"Group","Pane","ToolBar","Tab","TabItem","List","ListItem",
                         "Tree","TreeItem","Menu","MenuBar","Document"})
_NODE=re.compile(r'^(?P<indent> *)(?:\[(?P<id>e[1-9][0-9]{0,3})\] *)?'
                 r'(?P<role>[A-Za-z][A-Za-z0-9]*) +"(?P<name>[^"]*)"')
_WIN=re.compile(r'^Window: "[^"]*" \[pid ([1-9][0-9]*)\]')
_MCP_NODE=re.compile(r'^(?P<indent> *)(?:\[[0-9]{1,5}\] *)?'
                     r'(?P<role>[A-Za-z][A-Za-z0-9]*) +"(?P<name>[^"]*)"')
_LABEL=re.compile(r'^\s*\[(?P<label>[0-9]{1,5})\]\s+'
                  r'(?P<role>[A-Za-z][A-Za-z0-9]*)\s+"(?P<name>[^"]*)"')


def ancestors_for(tree, element_id):
    parents=[]
    for line in tree.splitlines():
        match=_NODE.match(line)
        if not match:continue
        indent=len(match.group("indent"))
        while parents and parents[-1][0]>=indent:parents.pop()
        if match.group("id")==element_id:
            return [entry for _,entry in parents][-8:]
        if match.group("role") in _PARENT_ROLES:
            parents.append((indent,{"control_type":match.group("role"),
                                    "name":match.group("name")}))
    return []


def labels_by_ancestry(snapshot,pid,kind,name,ancestors):
    """Return only labels in a matching named ancestry of the right PID."""
    if (type(ancestors) is not list or not 1<=len(ancestors)<=8 or
        any(type(node) is not dict or set(node)!={"control_type","name"}
            or node["control_type"] not in _PARENT_ROLES
            or type(node["name"]) is not str or len(node["name"])>240
            for node in ancestors)):
        raise ValueError("invalid accessible hierarchy")
    current_pid=None
    stack=[]
    result=[]
    in_tree=False
    for line in snapshot.splitlines():
        if line.strip()=="UI tree:":
            in_tree=True;continue
        if not in_tree:continue
        w=_WIN.match(line)
        if w:
            current_pid=int(w.group(1))
            stack=[]
            continue
        m=_MCP_NODE.match(line)
        if not m:continue
        indent=len(m.group("indent"))
        while stack and stack[-1][0]>=indent:stack.pop()
        match=_LABEL.match(line)
        if (match and current_pid==pid and match.group("role")==kind
            and match.group("name")==name and "(disabled)" not in line.lower()):
            actual=[entry for _,entry in stack]
            j=len(ancestors)-1
            for context in reversed(actual):
                if context==ancestors[j]:
                    j-=1
                    if j<0:
                        result.append(int(match.group("label")))
                        break
        if m.group("role") in _PARENT_ROLES:
            stack.append((indent,{"control_type":m.group("role"),
                                  "name":m.group("name")}))
    return result
