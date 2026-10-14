"""Project workspace records: panel identity is independent of tab/row hosting."""

from uuid import uuid4
import re

PROJECT_PANELS = {
    "project-structure": "STRUCTURE", "project-dictionary": "DICTIONARY",
    "project-conversations": "CONVERSATIONS", "project-ideas": "IDEAS",
    "project-whiteboard": "WHITEBOARD",
}
LAYOUT_EVENTS = {
    "CREATE_TAB", "SELECT_TAB", "RENAME_TAB", "DELETE_TAB", "ADD_ROW", "DELETE_ROW",
    "MOVE_ROW", "SET_ROW_COLUMNS", "SET_ROW_HEIGHT", "SET_SASH_PROPORTIONS",
    "SET_TAB_SCROLL", "HOST_PANEL", "UNHOST_PANEL", "CREATE_NOTES", "RENAME_PANEL",
    "DELETE_PANEL", "CREATE_PROJECT_PANEL", "CREATE_IMAGE",
}


def position_id(row_id, column):
    return f"{row_id}/column-{column}"


def make_default_workspace():
    document = {
        "version": 1, "selected-tab-id": "cockpit", "tabs": [
            {"id": "cockpit", "label": "Cockpit", "row-ids": ["overview", "working", "whiteboard"], "scroll-position": 0.0},
        ],
        "rows": {}, "positions": {}, "panels": {
            panel_id: {"id": panel_id, "type": kind, "label": kind.title(), "source": "project"}
            for panel_id, kind in PROJECT_PANELS.items()
        },
    }
    for row_id, height, panels in (
        ("overview", 230, ["project-structure", "project-dictionary"]),
        ("working", 290, ["project-conversations", "project-ideas"]),
        ("whiteboard", 240, ["project-whiteboard"]),
    ):
        count = len(panels)
        document["rows"][row_id] = {"column-count": count, "height": height,
                                     "sash-proportions": [i / count for i in range(1, count)]}
        for column, panel_id in enumerate(panels, 1):
            document["positions"][position_id(row_id, column)] = {"panel-id": panel_id}
    return document


def get_tab(document, tab_id):
    return next((tab for tab in document["tabs"] if tab["id"] == tab_id), None)


def get_tab_for_row(document, row_id):
    return next((tab for tab in document["tabs"] if row_id in tab["row-ids"]), None)


def get_tab_for_position(document, target):
    row_id = target.rsplit("/column-", 1)[0]
    return get_tab_for_row(document, row_id)


def get_hosted_panel_ids(document, tab_id):
    tab = get_tab(document, tab_id)
    return {
        document["positions"][position_id(row_id, column)]["panel-id"]
        for row_id in tab["row-ids"]
        for column in range(1, document["rows"][row_id]["column-count"] + 1)
    } - {None}


def add_empty_row(document, tab):
    row_id = uuid4().hex
    tab["row-ids"].append(row_id)
    document["rows"][row_id] = {"column-count": 1, "height": 260, "sash-proportions": []}
    document["positions"][position_id(row_id, 1)] = {"panel-id": None}


def remove_row(document, row_id):
    row = document["rows"].pop(row_id)
    for column in range(1, row["column-count"] + 1):
        del document["positions"][position_id(row_id, column)]


def apply_layout_event(document, event):
    """Apply one valid transition; expected invalid requests leave records unchanged."""
    kind = event["type"]
    tab = get_tab(document, event.get("tab-id", document["selected-tab-id"]))
    row_id = event.get("row-id")
    row = document["rows"].get(row_id)
    target = event.get("position-id")
    if kind == "CREATE_TAB":
        tab = {"id": uuid4().hex, "label": str(event.get("label") or "New tab"),
               "row-ids": [], "scroll-position": 0.0}
        document["tabs"].append(tab)
        add_empty_row(document, tab)
        document["selected-tab-id"] = tab["id"]
    elif kind in {"SELECT_TAB", "RENAME_TAB", "DELETE_TAB", "ADD_ROW"}:
        if tab is None:
            raise ValueError("That tab is no longer available.")
        if kind == "SELECT_TAB":
            document["selected-tab-id"] = tab["id"]
        elif kind == "RENAME_TAB":
            label = str(event["label"]).strip()
            if not label:
                raise ValueError("A tab needs a name.")
            tab["label"] = label
        elif kind == "ADD_ROW":
            add_empty_row(document, tab)
        else:
            if len(document["tabs"]) == 1:
                raise ValueError("Keep at least one tab.")
            for current_row in list(tab["row-ids"]):
                remove_row(document, current_row)
            document["tabs"].remove(tab)
            if document["selected-tab-id"] == tab["id"]:
                document["selected-tab-id"] = document["tabs"][0]["id"]
    elif kind in {"DELETE_ROW", "MOVE_ROW", "SET_ROW_COLUMNS", "SET_ROW_HEIGHT", "SET_SASH_PROPORTIONS"}:
        owner = get_tab_for_row(document, row_id)
        if row is None or owner is None:
            raise ValueError("That row is no longer available.")
        if kind == "DELETE_ROW":
            owner["row-ids"].remove(row_id)
            remove_row(document, row_id)
        elif kind == "MOVE_ROW":
            index = owner["row-ids"].index(row_id)
            destination = index + event["direction"]
            if 0 <= destination < len(owner["row-ids"]):
                owner["row-ids"][index], owner["row-ids"][destination] = owner["row-ids"][destination], row_id
        elif kind == "SET_ROW_COLUMNS":
            count = event["column-count"]
            if count not in (1, 2, 3):
                raise ValueError("Rows have one, two, or three columns.")
            old_count = row["column-count"]
            for column in range(count + 1, old_count + 1):
                del document["positions"][position_id(row_id, column)]
            for column in range(old_count + 1, count + 1):
                document["positions"][position_id(row_id, column)] = {"panel-id": None}
            if count != old_count:
                row["column-count"] = count
                row["sash-proportions"] = [i / count for i in range(1, count)]
        elif kind == "SET_ROW_HEIGHT":
            height = event["height"]
            if not isinstance(height, int) or not 120 <= height <= 10000:
                raise ValueError("Row height must be between 120 and 10000 pixels.")
            row["height"] = height
        else:
            proportions = event["proportions"]
            if (len(proportions) != row["column-count"] - 1
                    or any(not isinstance(p, (int, float)) or not 0 < p < 1 for p in proportions)
                    or any(a >= b for a, b in zip(proportions, proportions[1:]))):
                raise ValueError("Column dividers must be ordered within the row.")
            row["sash-proportions"] = list(proportions)
    elif kind == "SET_TAB_SCROLL":
        value = event["fraction"]
        if tab is None or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError("Invalid tab scroll position.")
        tab["scroll-position"] = value
    elif kind in {"HOST_PANEL", "UNHOST_PANEL", "CREATE_NOTES", "CREATE_PROJECT_PANEL", "CREATE_IMAGE"}:
        owner = get_tab_for_position(document, target)
        if target not in document["positions"] or owner is None:
            raise ValueError("That slot is no longer available.")
        if kind == "UNHOST_PANEL":
            document["positions"][target]["panel-id"] = None
        else:
            panel_id = event.get("panel-id")
            if kind == "CREATE_NOTES":
                panel_id = uuid4().hex
                document["panels"][panel_id] = {"id": panel_id, "type": "NOTES", "label": "Notes",
                                                "source": "workspace", "text": ""}
            elif kind == "CREATE_IMAGE":
                panel_id = uuid4().hex
                document["panels"][panel_id] = {"id": panel_id, "type": "IMAGE", "label": "Image",
                    "source": "workspace", "image-asset": None, "image-strokes": []}
            elif kind == "CREATE_PROJECT_PANEL":
                panel_id = next((key for key, value in PROJECT_PANELS.items() if value == event["panel-type"]), None)
                if panel_id is None or panel_id in document["panels"]:
                    raise ValueError("That project panel already exists or its type is unavailable.")
                document["panels"][panel_id] = {"id": panel_id, "type": event["panel-type"],
                    "label": event["panel-type"].title(), "source": "project"}
            elif panel_id not in document["panels"]:
                raise ValueError("That panel is no longer available.")
            current = document["positions"][target]["panel-id"]
            if panel_id != current and panel_id in get_hosted_panel_ids(document, owner["id"]):
                raise ValueError("A panel can appear only once in each tab. Unhost it from its current slot first.")
            document["positions"][target]["panel-id"] = panel_id
    elif kind == "DELETE_PANEL":
        panel_id = event["panel-id"]
        if panel_id not in document["panels"]:
            raise ValueError("That panel is no longer available.")
        del document["panels"][panel_id]
        for position in document["positions"].values():
            if position["panel-id"] == panel_id:
                position["panel-id"] = None
    elif kind == "RENAME_PANEL":
        panel = document["panels"].get(event["panel-id"])
        label = str(event["label"]).strip()
        if panel is None or not label:
            raise ValueError("A panel needs a name.")
        panel["label"] = label
    else:
        raise ValueError("Unknown workspace operation.")


def validate_workspace(document):
    """Validate stored/canonical boundaries; retain unknown extension fields."""
    if not isinstance(document, dict) or document.get("version") != 1:
        raise ValueError("Unsupported workspace format.")
    tabs, rows, positions, panels = (document[key] for key in ("tabs", "rows", "positions", "panels"))
    if not isinstance(tabs, list) or not tabs or any(not isinstance(value, dict) for value in (rows, positions, panels)):
        raise ValueError("Workspace needs tabs and record dictionaries.")
    tab_ids, row_ids, expected_positions = set(), set(), set()
    for panel_id, kind in PROJECT_PANELS.items():
        if panel_id not in panels:
            continue  # Deleted instruments stay absent until explicitly created again.
        panel = panels[panel_id]
        if panel.get("type") != kind or panel.get("source") != "project":
            raise ValueError("Workspace lost a project panel identity.")
    for panel_id, panel in panels.items():
        if panel.get("id") != panel_id or not isinstance(panel.get("label"), str):
            raise ValueError("Invalid panel identity.")
        if panel_id not in PROJECT_PANELS:
            if panel.get("type") == "NOTES" and isinstance(panel.get("text"), str):
                pass
            elif panel.get("type") == "IMAGE":
                asset = panel.get("image-asset")
                if asset is not None and not is_image_asset_reference(asset):
                    raise ValueError("Invalid image asset reference.")
                validate_image_strokes(panel.get("image-strokes", []))
            else:
                raise ValueError("Invalid workspace panel.")
    for tab in tabs:
        if tab["id"] in tab_ids or not isinstance(tab["label"], str) or not 0 <= tab.get("scroll-position", 0) <= 1:
            raise ValueError("Invalid tab identity or scroll position.")
        tab_ids.add(tab["id"])
        hosted = set()
        for row_id in tab["row-ids"]:
            if row_id in row_ids or row_id not in rows:
                raise ValueError("Rows must belong to exactly one tab.")
            row_ids.add(row_id)
            row = rows[row_id]
            count = row["column-count"]
            if count not in (1, 2, 3) or not isinstance(row["height"], int) or not 120 <= row["height"] <= 10000:
                raise ValueError("Invalid row dimensions.")
            proportions = row["sash-proportions"]
            if (len(proportions) != count - 1 or any(not 0 < p < 1 for p in proportions)
                    or any(a >= b for a, b in zip(proportions, proportions[1:]))):
                raise ValueError("Invalid row divider proportions.")
            for column in range(1, count + 1):
                target = position_id(row_id, column)
                expected_positions.add(target)
                panel_id = positions[target]["panel-id"]
                if panel_id is not None:
                    if panel_id not in panels or panel_id in hosted:
                        raise ValueError("Missing or duplicate panel hosting in a tab.")
                    hosted.add(panel_id)
    if set(rows) != row_ids or set(positions) != expected_positions or document["selected-tab-id"] not in tab_ids:
        raise ValueError("Workspace contains orphaned rows/slots or an invalid selection.")


def is_image_asset_reference(asset):
    return isinstance(asset, str) and re.fullmatch(r"assets/image-[0-9a-f]{32}\.(jpg|png|gif)", asset) is not None


def validate_image_strokes(strokes):
    if not isinstance(strokes, list):
        raise ValueError("Image strokes must be a list.")
    for stroke in strokes:
        if (not isinstance(stroke, dict) or stroke.get("color") != "#FF3030"
                or not isinstance(stroke.get("width"), (int, float)) or not 0 < stroke["width"] <= 10
                or not isinstance(stroke.get("points"), list) or not stroke["points"]):
            raise ValueError("Invalid image stroke.")
        for point in stroke["points"]:
            if (not isinstance(point, list) or len(point) != 2
                    or any(not isinstance(value, (int, float)) or not 0 <= value <= 1 for value in point)):
                raise ValueError("Invalid normalized image point.")
