"""Image request tokens and working drawing edits, owned exclusively by Core."""

from copy import deepcopy
from uuid import uuid4

from . import workspace

imports = {}  # Panel ID -> current import token.
previews = {}  # Panel ID -> current preview token.
errors = {}  # Presentation-only; never canonical.
EVENTS = {"IMPORT_IMAGE", "CLEAR_IMAGE", "IMAGE_PREVIEW", "IMAGE_IMPORTED",
          "IMAGE_PREVIEW_RETURNED", "IMAGE_STROKE_ADDED", "CLEAR_IMAGE_PEN", "SAVE_IMAGE"}


def initialize_image_state():
    for collection in (imports, previews, errors):
        collection.clear()


def get_rendering():
    return {key: {"busy": key in imports, "error": errors.get(key)} for key in set(imports) | set(errors)}


def forget_deleted_panels(panels):
    for collection in (imports, previews, errors):
        for key in list(collection):
            if key not in panels:
                del collection[key]


def reduce_image_event(event):
    from . import core
    panel_id = event["panel-id"]
    panel = core.documents["workspace"]["panels"].get(panel_id)
    if panel is None or panel["type"] != "IMAGE" or core.g["closing"]:
        return
    kind = event["type"]
    if kind == "IMPORT_IMAGE":
        if not core.g["initialized"]:
            errors[panel_id] = "Initialize PyDeck 26 before importing images."
            return
        token = uuid4().hex
        imports[panel_id] = token
        errors.pop(panel_id, None)
        core.effects.append({"type": "STACK", "registers": {
            "panel-id": panel_id, "request-id": token, "source": deepcopy(event["source"]),
        }, "frames": [{"machine": "CORE", "entry": "IMAGE_IMPORTED"},
                       {"machine": "IMAGE", "entry": "IMPORT_IMAGE"}]})
    elif kind == "IMAGE_IMPORTED":
        if imports.get(panel_id) != event["request-id"]:
            return
        del imports[panel_id]
        result = event["image-result"]
        if result["status"] == "error":
            errors[panel_id] = result["error"]
        else:
            panel["image-asset"] = result["image-asset"]
            panel["image-strokes"] = []
            previews.pop(panel_id, None)
            core.touch_document("workspace")
            core.request_commit({"workspace"})
    elif kind == "CLEAR_IMAGE":
        for collection in (imports, previews, errors):
            collection.pop(panel_id, None)
        panel["image-asset"] = None
        panel["image-strokes"] = []
        core.touch_document("workspace")
        core.request_commit({"workspace"})
    elif kind == "IMAGE_PREVIEW":
        if not panel.get("image-asset") or event["image-asset"] != panel["image-asset"]:
            return
        if not all(isinstance(event[key], int) and 0 < event[key] <= 20000 for key in ("width", "height")):
            return
        previews[panel_id] = event["request-id"]
        core.effects.append({"type": "STACK", "registers": {key: event[key] for key in (
            "panel-id", "request-id", "image-asset", "width", "height",
        )}, "frames": [{"machine": "CORE", "entry": "IMAGE_PREVIEW_RETURNED"},
                       {"machine": "IMAGE", "entry": "LOAD_PREVIEW"}]})
    elif kind == "IMAGE_PREVIEW_RETURNED":
        if previews.get(panel_id) != event["request-id"] or panel.get("image-asset") != event["image-asset"]:
            return
        previews.pop(panel_id, None)
        result = event["image-result"]
        if result["status"] == "error":
            errors[panel_id] = result["error"]
        else:
            core.effects.append({"type": "TK", "command": {
                "type": "SET_IMAGE_PREVIEW", "panel-id": panel_id,
                "request-id": event["request-id"], "image-asset": event["image-asset"],
                "bounds": [event["width"], event["height"]], **result,
            }})
    elif kind == "IMAGE_STROKE_ADDED":
        if not panel.get("image-asset") or panel["image-asset"] != event["image-asset"]:
            return
        try:
            workspace.validate_image_strokes([event["stroke"]])
        except ValueError as error:
            errors[panel_id] = str(error)
            return
        panel.setdefault("image-strokes", []).append(deepcopy(event["stroke"]))
        core.touch_document("workspace")
    elif kind == "CLEAR_IMAGE_PEN":
        if not panel.get("image-asset") or panel["image-asset"] != event["image-asset"]:
            return
        panel["image-strokes"] = []
        core.touch_document("workspace")
        core.request_commit({"workspace"})
    elif kind == "SAVE_IMAGE":
        core.request_commit({"workspace"})
