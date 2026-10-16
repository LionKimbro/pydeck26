"""Tk-owned internal panel dividers; semantic events persist their proportions."""

import tkinter as tk

g = {"window": None, "send": None}
splits = {}  # Panel ID -> live widgets, intended ratio, and deferred restoration.


def initialize_context(context):
    clear_panels()
    g.update(context)


def clear_panels():
    for split in splits.values():
        if split["restore-id"] is not None:
            try:
                g["window"].after_cancel(split["restore-id"])
            except tk.TclError:
                pass
    splits.clear()


def register_split(details):
    panel, pane = details["panel"], details["pane"]
    panel_id = panel["id"]
    splits[panel_id] = {"pane": pane, "proportion": panel.get("split-proportion", 0.4),
                        "restore-id": None, "restored-layout": None, "dragging": False}
    for widget in (pane, *pane.winfo_children()):
        widget.bind("<Configure>", lambda event, identity=panel_id: schedule_restoration(identity), add="+")
    pane.bind("<Map>", lambda event: schedule_restoration(panel_id), add="+")
    pane.bind("<ButtonPress-1>", lambda event: handle_when_drag_starts(event, panel_id), add="+")
    pane.bind("<ButtonRelease-1>", lambda event: handle_when_drag_ends(panel_id), add="+")
    schedule_restoration(panel_id)


def project_geometry(document):
    for panel_id, split in splits.items():
        record = document["panels"].get(panel_id)
        if record is None:
            continue
        proportion = record.get("split-proportion", 0.4)
        if proportion != split["proportion"]:
            split["proportion"] = proportion
            schedule_restoration(panel_id)


def schedule_restoration(panel_id):
    split = splits.get(panel_id)
    if split is not None and not split["dragging"] and split["restore-id"] is None:
        split["restore-id"] = g["window"].after_idle(lambda: restore_split(panel_id))


def restore_split(panel_id):
    split = splits.get(panel_id)
    if split is None:
        return
    split["restore-id"] = None
    pane = split["pane"]
    width = pane.winfo_width()
    if split["dragging"] or width <= 1 or not pane.winfo_ismapped():
        return
    layout = (width, split["proportion"], pane.sashpos(0))
    if layout == split["restored-layout"]:
        return
    pane.sashpos(0, round(width * split["proportion"]))
    split["restored-layout"] = (width, split["proportion"], pane.sashpos(0))


def handle_when_drag_starts(event, panel_id):
    split = splits[panel_id]
    split["dragging"] = split["pane"].identify(event.x, event.y) != ""


def handle_when_drag_ends(panel_id):
    split = splits[panel_id]
    if not split["dragging"]:
        return
    split["dragging"] = False
    pane = split["pane"]
    width = pane.winfo_width()
    if width > 1:
        proportion = pane.sashpos(0) / width
        if 0 < proportion < 1 and proportion != split["proportion"]:
            split["proportion"] = proportion
            g["send"]({"type": "SET_PANEL_SPLIT", "panel-id": panel_id, "proportion": proportion})
    schedule_restoration(panel_id)
