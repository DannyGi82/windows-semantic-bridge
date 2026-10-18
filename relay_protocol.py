"""Strictly read-only, bounded relay dispatcher. Action *plans* never execute UI input."""
from semantic_actions import SemanticActionPlanner, SemanticActionError, StaleSemanticState

class RelayDispatcher:
    _OPS = {
        "status":frozenset({"op"}),
        "watch":frozenset({"op","pid"}),
        "delta":frozenset({"op","revision"}),
        "snapshot":frozenset({"op"}),
        "stop":frozenset({"op"}),
        "shutdown":frozenset({"op"}),
        "prepare_action":frozenset({"op","name","action","revision"}),
        "prepare_element":frozenset({"op","element_id","action","revision"}),
        "prepare_current_action":frozenset({"op","name","action"}),
        "prepare_current_element":frozenset({"op","element_id","action"}),
        "verify_action":frozenset({"op","name","control_type","revision","expected_value"}),
        "verify_element":frozenset({"op","element_id","control_type","revision","expected_value"}),
        "verify_state":frozenset({"op","element_id","expected_state","revision"}),
        "verify_role_state":frozenset({"op","name","control_type","expected_state","revision"}),
    }
    def __init__(self, observer, bridge, watch_authorizer=None):
        self.watch_authorizer = watch_authorizer
        self.observer = observer
        self.bridge = bridge
        self.shutdown_requested = False
        self.planner = SemanticActionPlanner()

    def handle(self, payload):
        if not isinstance(payload,dict):
            return {"ok":False,"error":"INVALID_REQUEST"}
        op=payload.get("op")
        fields=self._OPS.get(op) if isinstance(op,str) else None
        if fields is None:
            return {"ok":False,"error":"OPERATION_DENIED"}
        if set(payload)!=fields:
            return {"ok":False,"error":"INVALID_REQUEST"}
        if op=="watch" and (type(payload.get("pid")) is not int or not 1<=payload["pid"]<=2**31-1):
            return {"ok":False,"error":"INVALID_REQUEST"}
        if op=="delta" and (type(payload.get("revision")) is not int or not 0<=payload["revision"]<=2**31-1):
            return {"ok":False,"error":"INVALID_REQUEST"}
        try:
            if op=="status": result=self.observer.status()
            elif op=="watch":
                if self.watch_authorizer is not None:
                    self.watch_authorizer(payload["pid"])
                result=self.observer.start(payload["pid"])
            elif op=="delta": result=self.observer.changes_since(payload["revision"])
            elif op=="snapshot": result=self.bridge.state()
            elif op=="prepare_action":
                state=self._fresh_semantic_state()
                result=self.planner.prepare(
                    state["text"], pid=state["pid"], revision=state["revision"],
                    expected_revision=payload["revision"],
                    name=payload["name"], action=payload["action"])
            elif op=="prepare_element":
                state=self._fresh_semantic_state()
                result=self.planner.prepare_by_id(
                    state["text"],pid=state["pid"],revision=state["revision"],
                    expected_revision=payload["revision"],element_id=payload["element_id"],
                    action=payload["action"])
            elif op=="prepare_current_action":
                state=self._fresh_semantic_state()
                result=self.planner.prepare(
                    state["text"],pid=state["pid"],revision=state["revision"],
                    expected_revision=state["revision"],
                    name=payload["name"],action=payload["action"])
            elif op=="prepare_current_element":
                state=self._fresh_semantic_state()
                result=self.planner.prepare_by_id(
                    state["text"],pid=state["pid"],revision=state["revision"],
                    expected_revision=state["revision"],
                    element_id=payload["element_id"],action=payload["action"])
            elif op=="verify_role_state":
                state=self._fresh_semantic_state(force=True)
                result=self.planner.verify_state_by_role(
                    state["text"],pid=state["pid"],revision=state["revision"],
                    after_revision=payload["revision"],name=payload["name"],
                    control_type=payload["control_type"],
                    expected_state=payload["expected_state"])
            elif op=="verify_state":
                state=self._fresh_semantic_state(force=True)
                result=self.planner.verify_state(
                    state["text"],pid=state["pid"],revision=state["revision"],
                    after_revision=payload["revision"],
                    element_id=payload["element_id"],
                    expected_state=payload["expected_state"])
            elif op=="verify_element":
                state=self._fresh_semantic_state(force=True)
                result=self.planner.verify_by_id(
                    state["text"],pid=state["pid"],revision=state["revision"],
                    after_revision=payload["revision"],element_id=payload["element_id"],
                    control_type=payload["control_type"],
                    expected_value=payload["expected_value"])
            elif op=="verify_action":
                state=self._fresh_semantic_state(force=True)
                result=self.planner.verify(
                    state["text"],pid=state["pid"],revision=state["revision"],
                    after_revision=payload["revision"],
                    name=payload["name"],control_type=payload["control_type"],
                    expected_value=payload["expected_value"])
            elif op=="stop": result=self.observer.stop()
            elif op=="shutdown":
                result=self.observer.stop()
                self.shutdown_requested=True
            else: return {"ok":False,"error":"OPERATION_DENIED"}
            return {"ok":True,"result":result}
        except StaleSemanticState:
            return {"ok":False,"error":"STALE_STATE"}
        except SemanticActionError:
            return {"ok":False,"error":"ELEMENT_UNAVAILABLE"}
        except AssertionError:
            return {"ok":False,"error":"POSTCONDITION_FAILED"}
        except PermissionError:
            return {"ok":False,"error":"NO_TARGET"}
        except (TypeError,ValueError):
            return {"ok":False,"error":"INVALID_REQUEST"}
        except Exception:
            # Never leak application/window content from exception messages.
            return {"ok":False,"error":"BACKEND_UNAVAILABLE"}
    def _fresh_semantic_state(self, *, force=False):
        pre=self.bridge.status()
        if pre.get("watching_pid") is None:
            raise PermissionError("no watched process")
        # Synchronous UIA reconciliation guards against a stale background
        # revision. The observer owns the same reentrant lock as poll().
        self.bridge.poll(force=force)
        status=self.bridge.status()
        if status.get("stale") or not status.get("snapshot_ready"):
            raise StaleSemanticState("no ready semantic state")
        state=self.bridge.state()
        if state["pid"] != status["watching_pid"]:
            raise StaleSemanticState("target identity changed")
        return state