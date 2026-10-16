"""Core-owned Git operation coordination and independent presentation records."""

from copy import deepcopy
from uuid import uuid4

g = {"snapshot": None, "active": None, "revision": 0, "refresh-pending": False,
     "message": "Choose Refresh to inspect this project's repository."}


def initialize_git_state():
    g.update({"snapshot": None, "active": None, "revision": 0, "refresh-pending": False,
              "message": "Choose Refresh to inspect this project's repository."})


def publish_git_state(extra=None):
    from . import core
    core.effects.append({"type": "TK", "command": {
        "type": "GIT_STATE", "snapshot": deepcopy(g["snapshot"]), "busy": g["active"] is not None,
        "revision": g["revision"], "message": g["message"], **(extra or {}),
    }})


def reduce_git_event(event):
    from . import core
    if event["type"] == "GIT_RETURNED":
        if g["active"] is None or event["request-id"] != g["active"]["id"]:
            return
        active = g["active"]
        g["active"] = None
        result = event["git-result"]
        if g["snapshot"] != result["snapshot"]:
            g["revision"] += 1
        g["snapshot"] = result["snapshot"]
        g["message"] = (active.get("previous-message") if active["operation"] == "status" and result["ok"]
                        else None) or result["message"]
        extra = {"ok": result["ok"], "operation": active["operation"],
                 "committed-message": active.get("message"), "viewer": result["viewer"]}
        if not core.g["closing"]:
            if result["open-path"]:
                core.effects.append({"type": "TK", "command": {"type": "OPEN_PATH", "path": result["open-path"]}})
            publish_git_state(extra)
            if g["refresh-pending"]:
                operation = g["refresh-pending"]
                g["refresh-pending"] = False
                reduce_git_event({"type": "GIT_REQUEST", "operation": operation})
        return
    operation = event["operation"]
    if g["active"] is not None:
        if operation in {"status", "refresh"}:
            g["refresh-pending"] = operation if operation == "refresh" else g["refresh-pending"] or "status"
        return
    snapshot = g["snapshot"]
    request = {"id": uuid4().hex, "operation": operation,
               "previous-message": g["message"] if snapshot is not None else None}
    if operation not in {"status", "refresh"}:
        if snapshot is None or event.get("revision") != g["revision"]:
            g["message"] = "Repository display changed. Review the current files and try again."
            publish_git_state()
            return
        request.update({"side": event.get("side"), "message": event.get("message", ""),
                        "index-stamp": snapshot["index-stamp"]})
        if operation in {"stage", "unstage", "revert", "discard", "file", "diff", "open"}:
            side = event.get("side")
            paths = event.get("paths", [])
            if side not in {"staged", "unstaged"}:
                return
            records = [deepcopy(record) for record in snapshot[side] if record["path"] in paths]
            if not records or len(records) != len(set(paths)):
                g["message"] = "Select files from the current repository display."
                publish_git_state()
                return
            request["records"] = records
            request["record"] = records[0]
    g["active"] = request
    if operation != "status":
        g["message"] = f"Git: {operation}…"
    publish_git_state()
    core.effects.append({"type": "STACK", "registers": {
        "request-id": request["id"], "project-root": core.g["snapshot"]["root"], "git-request": deepcopy(request),
    }, "frames": [{"machine": "CORE", "entry": "GIT_RETURNED"},
                   {"machine": {"new": "GIT"}, "entry": "OPERATE"}]})
