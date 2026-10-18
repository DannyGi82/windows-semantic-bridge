"""Read-only, fail-closed semantic action planning for Windows MCP.

Munim supplies UIA element identities and names. This module does NOT execute
any action, inject input, use screenshots, or bypass VisualGuard. It returns
an exact control target for the existing Windows MCP Invoke tool, which must
independently match its UI snapshot against the process PID and authorize.
"""
from __future__ import annotations
from semantic_hierarchy import ancestors_for
import re


class SemanticActionError(RuntimeError): pass
class AmbiguousElement(SemanticActionError): pass
class ElementUnavailable(SemanticActionError): pass
class StaleSemanticState(SemanticActionError): pass
class UnsupportedSemanticAction(SemanticActionError): pass


# Restricted, affirmative allowlist. The Windows MCP executor remains the only
# component allowed to actually apply a UI Automation action.
_CAPABILITIES = {
    "Edit": frozenset({"set_value"}),
    "Button": frozenset({"invoke"}),
    "Hyperlink": frozenset({"invoke"}),
    "CheckBox": frozenset({"toggle"}),
    "Switch": frozenset({"toggle"}),
    "RadioButton": frozenset({"select"}),
    "ListItem": frozenset({"select"}),
    "TabItem": frozenset({"select"}),
    "ComboBox": frozenset({"expand","collapse"}),
    "TreeItem": frozenset({"expand","collapse","select"}),
}
# Pattern is intentionally narrow: only elements carrying explicit Munim IDs
# are actionable. Do not synthesize controls from unlabeled text/OCR or title.
_LINE = re.compile(
    r'^\s*\[(?P<id>e[1-9]\d{0,3})\]\s+'
    r'(?P<kind>[A-Za-z][A-Za-z0-9]*)'
    r'(?:\s+"(?P<name>(?:[^"\\]|\\.)*)")?'
    r'(?:\s*=\s*"(?P<value>(?:[^"\\]|\\.)*)")?'
    r'(?P<flags>(?:\s+\([^)]*\))*)\s*$'
)


def elements(text: str) -> list[dict]:
    if not isinstance(text,str) or not text.strip():
        raise ElementUnavailable("semantic tree missing")
    found=[]
    for line in text.splitlines():
        m=_LINE.match(line)
        if not m:
            continue
        flags=m.group("flags").lower()
        found.append({
            "munim_id":m.group("id"),
            "control_type":m.group("kind"),
            "name":(m.group("name") or "").replace(r'\"','"'),
            "value":m.group("value").replace(r'\"','"') if m.group("value") is not None else None,
            "enabled":"(disabled)" not in flags,
            "state":next((word for word in ("checked","unchecked","mixed","selected","unselected","expanded","collapsed") if f" ({word})" in flags),None),
        })
    return found


def _selector(name: str) -> None:
    if not isinstance(name,str) or not name or name != name.strip() or len(name)>240 or any(c in name for c in '\r\n\x00'):
        raise ValueError("exact accessible name required")


def _one(tree: str, *, name: str, kind: str | None = None) -> dict:
    _selector(name)
    matches=[item for item in elements(tree) if item["name"]==name and (kind is None or item["control_type"]==kind)]
    if not matches:
        raise ElementUnavailable("element does not exist in the current semantic state")
    if len(matches)!=1:
        raise AmbiguousElement("element name is not unique; refine target")
    if not matches[0]["enabled"]:
        raise ElementUnavailable("element disabled")
    return matches[0]


class SemanticActionPlanner:
    def prepare(self, tree: str, *, pid: int, revision: int, expected_revision: int,
                name: str, action: str) -> dict:
        if type(pid) is not int or not 1<=pid<=2**31-1:
            raise ValueError("PID invalid")
        if type(revision) is not int or type(expected_revision) is not int or min(revision,expected_revision)<1:
            raise ValueError("revision invalid")
        if revision != expected_revision:
            raise StaleSemanticState("UI changed since the selected revision")
        _selector(name)
        item=_one(tree,name=name)
        if action not in _CAPABILITIES.get(item["control_type"],frozenset()):
            raise UnsupportedSemanticAction("action unsupported for selected UIA control")
        return {
            "pid":pid,"revision":revision,"action":action,
            "target":{k:item[k] for k in ("name","control_type","munim_id")},
            "executor":"Windows_MCP.Invoke","requires_visualguard":True,
            "execution_performed":False,
        }

    def verify(self, tree: str, *, pid: int, revision: int, after_revision: int,
               name: str, control_type: str, expected_value: str) -> dict:
        if type(pid) is not int or pid < 1:
            raise ValueError("PID invalid")
        if type(revision) is not int or type(after_revision) is not int or after_revision<0:
            raise ValueError("revision invalid")
        if revision <= after_revision:
            raise StaleSemanticState("no newer semantic revision was observed")
        if not isinstance(expected_value,str) or len(expected_value)>2048:
            raise ValueError("invalid verification value")
        element=_one(tree,name=name,kind=control_type)
        if element["value"] != expected_value:
            raise AssertionError("UIA semantic postcondition not satisfied")
        return {"verified":True,"pid":pid,"revision":revision,
                "control_type":control_type,"name":name}
    def prepare_by_id(self, tree: str, *, pid: int, revision: int,
                      expected_revision: int, element_id: str, action: str) -> dict:
        if type(pid) is not int or not 1 <= pid <= 2**31-1:
            raise ValueError("invalid PID")
        if type(revision) is not int or type(expected_revision) is not int or min(revision,expected_revision)<1:
            raise ValueError("invalid revision")
        if revision != expected_revision:
            raise StaleSemanticState("UI state revision no longer matches")
        item=self._one_id(tree,element_id)
        if action not in _CAPABILITIES.get(item["control_type"],frozenset()):
            raise UnsupportedSemanticAction("action not permitted for selected pattern")
        return {"pid":pid,"revision":revision,"action":action,
                "target":dict({k:item[k] for k in ("munim_id","name","control_type")}, **({"ancestors":ancestors_for(tree,element_id)} if ancestors_for(tree,element_id) else {})),
                "executor":"Windows_MCP.Invoke","requires_visualguard":True,
                "execution_performed":False}

    def verify_by_id(self, tree: str, *, pid: int, revision: int,
                     after_revision: int, element_id: str, control_type: str,
                     expected_value: str) -> dict:
        if type(pid) is not int or pid<1 or type(revision) is not int or type(after_revision) is not int:
            raise ValueError("invalid PID or revision")
        if revision <= after_revision:
            raise StaleSemanticState("semantic revision did not advance")
        if not isinstance(expected_value,str) or len(expected_value)>2048:
            raise ValueError("invalid verification value")
        item=self._one_id(tree,element_id)
        if item["control_type"] != control_type or item["value"] != expected_value:
            raise AssertionError("semantic postcondition not satisfied")
        return {"verified":True,"pid":pid,"revision":revision,"munim_id":element_id}

    @staticmethod
    def _one_id(tree: str, element_id: str) -> dict:
        if not isinstance(element_id,str) or re.fullmatch(r'e[1-9]\d{0,3}',element_id) is None:
            raise ValueError("invalid Munim element ID")
        candidates=[item for item in elements(tree) if item["munim_id"]==element_id]
        if len(candidates)!=1 or not candidates[0]["enabled"]:
            raise ElementUnavailable("element ID not present, ambiguous or disabled")
        return candidates[0]
    def verify_state(self, tree: str, *, pid: int, revision: int,
                     after_revision: int, element_id: str, expected_state: str) -> dict:
        if type(pid) is not int or pid < 1:
            raise ValueError("invalid PID")
        if type(revision) is not int or type(after_revision) is not int or after_revision < 0:
            raise ValueError("invalid revision")
        if revision <= after_revision:
            raise StaleSemanticState("UI state did not advance")
        if expected_state not in ("checked","unchecked","mixed","selected",
                                  "unselected","expanded","collapsed"):
            raise ValueError("invalid postcondition")
        item=self._one_id(tree,element_id)
        if item["state"] is None:
            raise ElementUnavailable("semantic state not provided by UI Automation")
        if item["state"] != expected_state:
            raise AssertionError("state postcondition failed")
        return {"verified":True,"pid":pid,"revision":revision,
                "munim_id":element_id,"observed_state":item["state"]}
    def verify_state_by_role(self, tree: str, *, pid: int, revision: int,
                             after_revision: int, name: str, control_type: str,
                             expected_state: str) -> dict:
        if type(pid) is not int or pid < 1 or type(revision) is not int or type(after_revision) is not int:
            raise ValueError("invalid PID or revision")
        if revision <= after_revision:
            raise StaleSemanticState("no new semantic state")
        if not isinstance(name,str) or len(name)>240 or any(c in name for c in "\r\n\x00"):
            raise ValueError("invalid name")
        if not isinstance(control_type,str) or control_type not in _CAPABILITIES:
            raise ValueError("invalid control type")
        if expected_state not in ("checked","unchecked","mixed","selected","unselected","expanded","collapsed"):
            raise ValueError("invalid postcondition state")
        matches=[item for item in elements(tree)
                 if item["control_type"]==control_type and item["name"]==name]
        if len(matches)>1:
            raise AmbiguousElement("same role and name occur more than once")
        if not matches or not matches[0]["enabled"] or matches[0]["state"] is None:
            raise ElementUnavailable("accessible state missing or control unavailable")
        if matches[0]["state"]!=expected_state:
            raise AssertionError("semantic state postcondition failed")
        return {"verified":True,"pid":pid,"revision":revision,
                "control_type":control_type,"name":name,
                "observed_state":expected_state}