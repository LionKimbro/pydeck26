"""Core machine: project working copies, semantic reduction, and effects."""

from copy import deepcopy
from datetime import date, datetime
import json
from pathlib import Path
import re
from uuid import uuid4

from . import machine, mobile_stacks as ms, workspace

g = {
    "revision": 0, "ready": False, "initialized": False, "seq": 0,
    "snapshot": None, "selected-conversation-id": None,
    "view-index": 0, "view-text": "", "virtual-snapshot": None,
    "history-token": 0, "closing": False, "commit": None,
    "status": "Opening PyDeck 26.", "load-pending": False,
    "outstanding": 0, "stop-requested": False,
}
documents = {}  # Working copies; Mem is canonical.
generations = {}
dirty = set()
requested = set()  # Coalesced persistence requests while a commit is in flight.
history = []
events = []
effects = []


def initialize_core_state():
    g.update({"revision": 0, "ready": False, "initialized": False, "seq": 0,
              "snapshot": None, "selected-conversation-id": None,
              "view-index": 0, "view-text": "", "virtual-snapshot": None,
              "history-token": 0, "closing": False, "commit": None,
              "status": "Opening PyDeck 26.", "load-pending": False,
              "outstanding": 0, "stop-requested": False})
    for collection in (documents, generations, dirty, requested, history, events, effects):
        collection.clear()


def touch_document(key):
    generations[key] += 1
    dirty.add(key)


def get_conversation(item_id):
    return next((item for item in documents["conversations"]["items"]
                 if item.get("id") == item_id), None)


def get_history_items():
    virtual = [g["virtual-snapshot"]] if g["virtual-snapshot"] else []
    return virtual + [{"kind": "snapshot", "path": path} for path in history]


def publish_view():
    effects.append({"type": "TK", "command": {
        "type": "STATE", "seq": g["seq"], "ready": g["ready"],
        "initialized": g["initialized"], "snapshot": deepcopy(g["snapshot"]),
        "documents": deepcopy(documents), "dirty": sorted(dirty),
        "selected-conversation-id": g["selected-conversation-id"],
        "view-index": g["view-index"], "view-text": g["view-text"],
        "history-count": len(get_history_items()), "status": g["status"],
    }})


def request_commit(keys):
    if not g["initialized"]:
        g["status"] = "Initialize PyDeck 26 before saving project state."
        return
    requested.update(keys)
    dispatch_pending_commit_when_idle()


def dispatch_pending_commit_when_idle():
    if g["commit"] is not None or not requested:
        return
    keys = set(requested)
    requested.clear()
    packet = {
        "base-revision": g["revision"],
        "documents": deepcopy({key: documents[key] for key in keys}),
        "generations": {key: generations[key] for key in keys},
    }
    g["commit"] = packet["generations"]
    g["status"] = "Saving project state…"
    effects.append({"type": "STACK", "registers": packet, "frames": [
        {"machine": "CORE", "entry": "COMMIT_RETURNED"},
        {"machine": "MEM", "entry": "COMMIT_PROJECT"},
    ]})


def finish_close_when_saved():
    if (not g["closing"] or g["commit"] is not None or requested
            or g["load-pending"] or g["outstanding"] or g["stop-requested"]):
        return
    if dirty and g["initialized"]:
        request_commit(dirty)
        return
    g["stop-requested"] = True
    effects.append({"type": "STOP"})


def reduce_event(event):
    kind = event["type"]
    if kind in HANDLERS:
        g["outstanding"] -= 1
    g["seq"] = max(g["seq"], event.get("seq", 0))
    if kind == "START" or kind == "INITIALIZE":
        if g["load-pending"] or (kind == "INITIALIZE" and g["initialized"]):
            return
        g["load-pending"] = True
        effects.append({"type": "STACK", "registers": {"initialize": kind == "INITIALIZE"},
                        "frames": [
                            {"machine": "CORE", "entry": "PROJECT_RETURNED"},
                            {"machine": "MEM", "entry": "INSTALL_PROJECT"},
                            {"machine": "DISK", "entry": "LOAD_PROJECT"},
                        ]})
        return
    if kind == "PROJECT_RETURNED":
        bundle = event["bundle"]
        retained = deepcopy({key: documents[key] for key in dirty})
        documents.update({key: bundle[key] for key in (
            "whiteboard", "dictionary", "conversations", "ideas", "resources", "workspace",
        )})
        documents.update(retained)
        g["snapshot"] = bundle["snapshot"]
        if documents["dictionary"] is None:
            name = bundle["snapshot"]["identity"].get("name") or Path(bundle["snapshot"]["root"]).name
            documents["dictionary"] = {"id": name, "identity": {"name": name}}
        identity = documents["dictionary"].get("identity")
        if not isinstance(identity, dict):
            identity = {}
            documents["dictionary"]["identity"] = identity
        name = identity.setdefault("name", Path(bundle["snapshot"]["root"]).name)
        documents["dictionary"].setdefault("id", name)
        identity.setdefault("title", re.sub(r"(?<=\D)(?=\d)", " ", name.replace("-", " ").replace("_", " ")).title())
        identity.setdefault("tags", [])
        identity.setdefault("hook", "")
        for key in documents:
            generations.setdefault(key, 0)
        history[:] = bundle["history"]
        g["revision"] = event["revision"]
        g["initialized"] = bundle["initialized"]
        g["ready"] = True
        g["load-pending"] = False
        g["view-text"] = documents["whiteboard"]
        items = documents["conversations"]["items"]
        if items:
            g["selected-conversation-id"] = max(items, key=lambda item: str(item.get("date") or ""))["id"]
        g["status"] = "Current" if g["initialized"] else "Initialize PyDeck 26 to save project state."
    elif kind == "COMMIT_RETURNED":
        g["revision"] = event["revision"]
        for key, generation in event["generations"].items():
            if generations[key] == generation:
                dirty.discard(key)
        g["commit"] = None
        g["status"] = ("Saved earlier changes; newer edits remain unsaved."
                       if dirty else "Project state saved.")
        dispatch_pending_commit_when_idle()
    elif kind == "SHUTDOWN":
        g["closing"] = True
        machine.shutdown_started.set()
        if g["initialized"]:
            request_commit(dirty)
    elif not g["ready"] or g["closing"]:
        finish_close_when_saved()
        return
    elif kind == "SAVE":
        request_commit(dirty | {"whiteboard", "workspace"})
    elif kind in workspace.LAYOUT_EVENTS:
        proposal = deepcopy(documents["workspace"])
        try:
            workspace.apply_layout_event(proposal, event)
            workspace.validate_workspace(proposal)
        except ValueError as error:
            g["status"] = str(error)
        else:
            if proposal != documents["workspace"]:
                documents["workspace"] = proposal
                touch_document("workspace")
                request_commit({"workspace"})
    elif kind == "NOTES_EDIT":
        panel = documents["workspace"]["panels"].get(event["panel-id"])
        if panel is not None and panel["type"] == "NOTES" and panel["text"] != event["text"]:
            panel["text"] = event["text"]
            touch_document("workspace")
    elif kind == "DICTIONARY_EDIT":
        documents["dictionary"]["identity"].update(event["identity"])
        touch_document("dictionary")
    elif kind == "DICTIONARY_ADDITIONAL":
        document = documents["dictionary"]
        for key in list(document):
            if key not in {"id", "identity"}:
                del document[key]
        document.update(event["additional"])
        touch_document("dictionary")
        request_commit({"dictionary"})
    elif kind == "SELECT_CONVERSATION":
        g["selected-conversation-id"] = event["id"]
    elif kind == "NEW_CONVERSATION":
        item = {"id": str(uuid4()), "date": date.today().isoformat(), "title": "",
                "url": "", "hook": "", "description": ""}
        documents["conversations"]["items"].append(item)
        g["selected-conversation-id"] = item["id"]
        touch_document("conversations")
        g["status"] = "New conversation created in memory."
    elif kind == "CONVERSATION_EDIT":
        item = get_conversation(event["id"])
        if item is not None:
            item.update(event["fields"])
            touch_document("conversations")
            g["status"] = "Conversation saved in memory."
    elif kind == "IDEA_SAVE":
        items = documents["ideas"]["items"]
        item = deepcopy(event["item"])
        existing = next((old for old in items if old["guid"] == item["guid"]), None)
        if existing is None:
            items.append(item)
        else:
            existing.update(item)
        touch_document("ideas")
        request_commit({"ideas"})
    elif kind == "RESOURCE_ADD":
        selected = Path(event["path"])
        root = Path(g["snapshot"]["root"])
        try:
            parent = selected.parent.relative_to(root).as_posix()
            parent = f"{parent}/" if parent != "." else ""
        except ValueError:
            parent = str(selected.parent)
        documents["resources"]["items"].append({"path": parent, "filename": selected.name,
            "hook": "(double-click to assign hook)", "kind": event["kind"]})
        touch_document("resources")
        request_commit({"resources"})
    elif kind in {"RESOURCE_EDIT", "RESOURCE_REMOVE", "RESOURCE_MOVE"}:
        items = documents["resources"]["items"]
        index = event["index"]
        if not 0 <= index < len(items):
            return
        if kind == "RESOURCE_EDIT":
            items[index].update(event["item"])
        elif kind == "RESOURCE_REMOVE":
            del items[index]
        else:
            target = index + event["change"]
            if not 0 <= target < len(items):
                return
            items[index], items[target] = items[target], items[index]
        touch_document("resources")
        request_commit({"resources"})
    elif kind == "COPY_STRUCTURE":
        effects.append({"type": "STACK", "registers": {
            "items": deepcopy(documents["resources"]["items"]),
        }, "frames": [{"machine": "CORE", "entry": "STRUCTURE_RETURNED"},
                       {"machine": "DISK", "entry": "STRUCTURE_PATHS"}]})
    elif kind == "STRUCTURE_RETURNED":
        effects.append({"type": "TK", "command": {
            "type": "COPY_TEXT", "text": json.dumps(event["items"], indent=2, ensure_ascii=False),
        }})
    elif kind == "RESOURCE_ACTION":
        effects.append({"type": "STACK", "registers": {
            "item": deepcopy(event["item"]), "action": event["action"],
        }, "frames": [{"machine": "CORE", "entry": "RESOURCE_RETURNED"},
                       {"machine": "DISK", "entry": "RESOURCE_PATH"}]})
    elif kind == "RESOURCE_RETURNED":
        if event["error"]:
            g["status"] = event["error"]
        else:
            effects.append({"type": "TK", "command": {
                "type": event["action"], "path": event["path"],
            }})
    elif kind == "WHITEBOARD_EDIT":
        if not g["initialized"]:
            return
        g["history-token"] += 1
        if g["view-index"]:
            g["virtual-snapshot"] = {"kind": "virtual", "text": documents["whiteboard"],
                                     "created-at": datetime.now()}
        g["view-index"] = 0
        documents["whiteboard"] = event["text"]
        g["view-text"] = event["text"]
        touch_document("whiteboard")
        g["status"] = "Current"
    elif kind == "HISTORY_SELECT":
        index = event["index"]
        items = get_history_items()
        if not 0 <= index <= len(items):
            return
        g["history-token"] += 1
        if index == 0:
            g["view-index"] = 0
            g["view-text"] = documents["whiteboard"]
            g["status"] = "Current"
        else:
            item = items[index - 1]
            if item["kind"] == "virtual":
                g["view-index"] = index
                g["view-text"] = item["text"]
                g["status"] = f"Virtual snapshot: {item['created-at']:%Y-%m-%d %H:%M:%S}"
            else:
                effects.append({"type": "STACK", "registers": {
                    "path": item["path"], "index": index, "token": g["history-token"],
                }, "frames": [{"machine": "CORE", "entry": "HISTORY_RETURNED"},
                               {"machine": "DISK", "entry": "READ_HISTORY"}]})
    elif kind == "HISTORY_RETURNED":
        if event["token"] != g["history-token"]:
            return
        g["view-index"] = event["index"]
        g["view-text"] = event["text"]
        g["status"] = f"Snapshot: {event['path'].stem}"
    elif kind == "SNAPSHOT":
        if not g["initialized"]:
            g["status"] = "Initialize PyDeck 26 before creating a snapshot."
        elif g["view-index"]:
            g["status"] = "Only Current can be snapshotted."
        else:
            effects.append({"type": "STACK", "registers": {"text": documents["whiteboard"]},
                            "frames": [{"machine": "CORE", "entry": "SNAPSHOT_RETURNED"},
                                       {"machine": "DISK", "entry": "SNAPSHOT"}]})
    elif kind == "SNAPSHOT_RETURNED":
        history[:] = event["history"]
        g["status"] = event["error"] or "Snapshot saved."
    elif kind == "STATUS":
        g["status"] = event["text"]
    finish_close_when_saved()
    publish_view()


def dispatch_effect(effect):
    if effect["type"] == "TK":
        machine.machines["CORE"]["commands"].put(effect["command"])
    elif effect["type"] == "STACK":
        g["outstanding"] += 1
        ms.create_stack()
        for key, value in effect["registers"].items():
            ms.set_register((key, value))
        for frame in effect["frames"]:
            ms.push_frame(frame)
        machine.route_current_stack()
    elif effect["type"] == "STOP":
        machine.machines["MEM"]["inbox"].put(None)
        machine.request_machine_retirement()
        machine.machines["CORE"]["commands"].put({"type": "SHUTDOWN_COMPLETE"})


def handle_when_core_receives_stack_result():
    # Copy before runtime pops or forwards the traveling stack.
    event = deepcopy(ms.stack()["registers"])
    event["type"] = ms.stack()["frames"][-1]["entry"]
    events.append(event)


HANDLERS = {name: handle_when_core_receives_stack_result for name in (
    "PROJECT_RETURNED", "COMMIT_RETURNED", "HISTORY_RETURNED",
    "SNAPSHOT_RETURNED", "RESOURCE_RETURNED", "STRUCTURE_RETURNED",
)}


def run_reducer_core():
    initialize_core_state()
    events.append({"type": "START"})
    runtime = machine.get_current_runtime()
    while runtime["running"] and not machine.fatal.is_set():
        while events and not machine.fatal.is_set():
            reduce_event(events.pop(0))
        while effects and not machine.fatal.is_set():
            dispatch_effect(effects.pop(0))
        if not runtime["running"]:
            return
        item = runtime["inbox"].get()
        if machine.fatal.is_set():
            return
        if ms.is_mobile_stack(item):
            machine.handle_received_mobile_stack(item)
        else:
            events.append(item if item is not None else {"type": "SHUTDOWN"})
