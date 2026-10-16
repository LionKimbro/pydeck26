"""Tk image canvases and red-pen drafts; acquisition and decoding stay in workers."""

from copy import deepcopy
from uuid import uuid4
import tkinter as tk
from tkinter import filedialog, ttk

from .theme import COLORS
from PIL import Image, ImageTk
from tkinterdnd2 import DND_FILES

g = {"send": None, "window": None, "is-closing": None}
panels = {}  # Active Tk hosts by independent panel ID.


def initialize_context(context):
    clear_panels()
    g.update(context)


def clear_panels():
    for panel in panels.values():
        panel["active"] = False
        for key in ("resize-id", "save-id"):
            if panel[key] is not None:
                try:
                    g["window"].after_cancel(panel[key])
                except tk.TclError:
                    pass
    panels.clear()


def build_panel(details):
    record, parent = details["panel"], details["parent"]
    header = tk.Frame(parent, background=COLORS["panel"])
    header.grid(row=0, column=0, sticky="ew", padx=10, pady=6)
    tk.Label(header, text="IMAGE", background=COLORS["panel"], foreground=COLORS["accent"],
             font=("TkDefaultFont", 12, "bold")).pack(side="left")
    parent.rowconfigure(0, weight=0)
    parent.rowconfigure(1, weight=1)
    canvas = tk.Canvas(parent, background=COLORS["editor"], highlightthickness=0, width=120, height=180)
    canvas.grid(row=1, column=0, sticky="nsew", padx=8)
    controls = ttk.Frame(parent, padding=5)
    controls.grid(row=2, column=0, sticky="ew")
    status = ttk.Label(parent, anchor="w", wraplength=250)
    status.grid(row=3, column=0, sticky="ew", padx=8)
    panel = {"id": record["id"], "canvas": canvas, "active": True, "asset": None,
             "photo": None, "item": None, "requested": None, "token": None,
             "resize-id": None, "save-id": None, "busy": False, "status": status,
             "strokes": [], "stroke": None, "pen-enabled": False,
             "placeholder": canvas.create_text(0, 0, text="Drop a JPEG, PNG, or GIF here", fill=COLORS["secondary"])}
    panel["empty-controls"] = ttk.Frame(controls)
    panel["empty-controls"].pack(side="left")
    panel["paste"] = ttk.Button(panel["empty-controls"], text="Paste from Clipboard",
                                 command=lambda: send_import(panel, {"kind": "clipboard"}))
    panel["paste"].pack(side="left")
    panel["browse"] = ttk.Button(panel["empty-controls"], text="Browse for Image…",
                                  command=lambda: handle_when_user_browses_image(panel))
    panel["browse"].pack(side="left", padx=4)
    panel["clear"] = ttk.Button(controls, text="Clear image", command=lambda: handle_when_user_clears_image(panel))
    panel["clear-pen"] = ttk.Button(controls, text="Clear pen", command=lambda: handle_when_user_clears_pen(panel))
    panel["pen"] = ttk.Button(controls, text="Red pen", command=lambda: handle_when_user_toggles_pen(panel))
    canvas.bind("<Configure>", lambda event: handle_when_image_canvas_resizes(panel))
    canvas.bind("<Map>", lambda event: handle_when_image_canvas_resizes(panel))
    canvas.bind("<ButtonPress-1>", lambda event: handle_when_image_stroke_starts(event, panel))
    canvas.bind("<B1-Motion>", lambda event: handle_when_image_stroke_moves(event, panel))
    canvas.bind("<ButtonRelease-1>", lambda event: handle_when_image_stroke_ends(event, panel))
    canvas.drop_target_register(DND_FILES)
    canvas.dnd_bind("<<Drop>>", lambda event: handle_when_user_drops_image(event, panel))
    panels[record["id"]] = panel
    return header


def project_panels(document, states):
    for panel_id, panel in panels.items():
        record = document["panels"][panel_id]
        asset = record.get("image-asset")
        if asset != panel["asset"]:
            panel.update({"asset": asset, "photo": None, "requested": None,
                          "token": None, "stroke": None, "pen-enabled": False})
            panel["canvas"].configure(cursor="")
            panel["pen"].state(["!pressed"])
            if panel["item"] is not None:
                panel["canvas"].delete(panel["item"])
                panel["item"] = None
        panel["strokes"] = deepcopy(record.get("image-strokes", []))
        state = states.get(panel_id, {})
        panel["busy"] = state.get("busy", False)
        panel["status"].configure(text=state.get("error") or ("Importing image…" if panel["busy"] else ""))
        if asset:
            panel["empty-controls"].pack_forget()
            panel["pen"].pack(side="left", padx=4)
        else:
            panel["empty-controls"].pack(side="left")
            panel["pen"].pack_forget()
        if asset or panel["busy"]:
            panel["clear-pen"].pack(side="right")
            panel["clear"].pack(side="right")
        else:
            panel["clear-pen"].pack_forget()
            panel["clear"].pack_forget()
        panel["clear-pen"].configure(state="normal" if asset and not panel["busy"] else "disabled")
        for key in ("paste", "browse"):
            panel[key].configure(state="disabled" if panel["busy"] else "normal")
        panel["pen"].configure(state="normal" if panel["photo"] and not panel["busy"] else "disabled")
        panel["canvas"].itemconfigure(panel["placeholder"],
            state="hidden" if panel["photo"] else "normal", text="Loading image…" if asset else "Drop a JPEG, PNG, or GIF here")
        handle_when_image_canvas_resizes(panel)


def handle_when_user_browses_image(panel):
    if panel["busy"] or g["is-closing"]():
        return
    path = filedialog.askopenfilename(parent=g["window"], title="Choose an image",
        filetypes=[("Images", "*.jpg *.jpeg *.png *.gif"), ("All files", "*.*")])
    if path:
        send_import(panel, {"kind": "file", "path": path})


def send_import(panel, source):
    if not panel["active"] or panel["busy"] or g["is-closing"]():
        return
    panel["busy"] = True
    panel["status"].configure(text="Importing image…")
    g["send"]({"type": "IMPORT_IMAGE", "panel-id": panel["id"], "source": source})


def handle_when_user_drops_image(event, panel):
    if panel["asset"] or panel["busy"] or not panel["active"] or g["is-closing"]():
        return "none"
    paths = panel["canvas"].tk.splitlist(event.data)
    if len(paths) != 1:
        panel["status"].configure(text="Drop one image file at a time.")
        return "none"
    send_import(panel, {"kind": "file", "path": paths[0]})
    return "copy"


def handle_when_user_clears_image(panel):
    if panel["save-id"] is not None:
        g["window"].after_cancel(panel["save-id"])
        panel["save-id"] = None
    panel.update({"stroke": None, "token": None, "requested": None})
    g["send"]({"type": "CLEAR_IMAGE", "panel-id": panel["id"]})


def handle_when_user_clears_pen(panel):
    if not panel["active"] or not panel["asset"] or panel["busy"] or g["is-closing"]():
        return
    if panel["save-id"] is not None:
        g["window"].after_cancel(panel["save-id"])
        panel["save-id"] = None
    panel.update({"stroke": None, "strokes": []})
    render_strokes(panel)
    g["send"]({"type": "CLEAR_IMAGE_PEN", "panel-id": panel["id"], "image-asset": panel["asset"]})


def handle_when_image_canvas_resizes(panel):
    if not panel["active"]:
        return
    canvas = panel["canvas"]
    center = (canvas.winfo_width() / 2, canvas.winfo_height() / 2)
    canvas.coords(panel["placeholder"], *center)
    canvas.itemconfigure(panel["placeholder"], width=max(1, canvas.winfo_width() - 20))
    if panel["item"] is not None:
        canvas.coords(panel["item"], *center)
    render_strokes(panel)
    bounds = (panel["asset"], canvas.winfo_width(), canvas.winfo_height())
    if not panel["asset"] or bounds == panel["requested"] or min(bounds[1:]) < 2:
        return
    if panel["resize-id"] is not None:
        g["window"].after_cancel(panel["resize-id"])
    panel["resize-id"] = g["window"].after(100, lambda: handle_when_preview_debounce_expires(panel))


def handle_when_preview_debounce_expires(panel):
    panel["resize-id"] = None
    if not panel["active"] or not panel["asset"] or g["is-closing"]():
        return
    canvas = panel["canvas"]
    width, height = canvas.winfo_width(), canvas.winfo_height()
    panel["requested"] = (panel["asset"], width, height)
    panel["token"] = uuid4().hex
    g["send"]({"type": "IMAGE_PREVIEW", "panel-id": panel["id"], "image-asset": panel["asset"],
               "width": width, "height": height, "request-id": panel["token"]})


def apply_preview(command):
    panel = panels.get(command["panel-id"])
    if panel is None or not panel["active"] or panel["token"] != command["request-id"]:
        return
    canvas = panel["canvas"]
    if panel["asset"] != command["image-asset"] or command["bounds"] != [canvas.winfo_width(), canvas.winfo_height()]:
        return
    prepared = Image.frombytes("RGBA", (command["width"], command["height"]), command["pixels"])
    panel["photo"] = ImageTk.PhotoImage(prepared, master=canvas)
    if panel["item"] is not None:
        canvas.delete(panel["item"])
    panel["item"] = canvas.create_image(canvas.winfo_width() / 2, canvas.winfo_height() / 2, image=panel["photo"])
    canvas.itemconfigure(panel["placeholder"], state="hidden")
    panel["pen"].configure(state="normal")
    render_strokes(panel)


def handle_when_user_toggles_pen(panel):
    finish_stroke(panel)
    if not panel["photo"]:
        return
    panel["pen-enabled"] = not panel["pen-enabled"]
    panel["canvas"].configure(cursor="crosshair" if panel["pen-enabled"] else "")
    panel["pen"].state(["pressed"] if panel["pen-enabled"] else ["!pressed"])


def get_image_point(event, panel):
    photo, canvas = panel["photo"], panel["canvas"]
    return [(event.x - (canvas.winfo_width() - photo.width()) / 2) / photo.width(),
            (event.y - (canvas.winfo_height() - photo.height()) / 2) / photo.height()]


def handle_when_image_stroke_starts(event, panel):
    if not panel["active"] or not panel["pen-enabled"] or not panel["photo"] or panel["busy"] or g["is-closing"]():
        return
    point = get_image_point(event, panel)
    if any(value < 0 or value > 1 for value in point):
        return
    panel["stroke"] = {"points": [point], "color": "#FF3030", "width": 3 / min(panel["photo"].width(), panel["photo"].height())}
    render_strokes(panel)


def handle_when_image_stroke_moves(event, panel):
    if panel["stroke"] is not None:
        point = [max(0, min(1, value)) for value in get_image_point(event, panel)]
        if point != panel["stroke"]["points"][-1]:
            panel["stroke"]["points"].append(point)
        render_strokes(panel)


def handle_when_image_stroke_ends(event, panel):
    handle_when_image_stroke_moves(event, panel)
    finish_stroke(panel)


def finish_stroke(panel):
    stroke = panel["stroke"]
    if stroke is None:
        return
    panel["stroke"] = None
    panel["strokes"].append(deepcopy(stroke))
    g["send"]({"type": "IMAGE_STROKE_ADDED", "panel-id": panel["id"], "image-asset": panel["asset"], "stroke": stroke})
    if panel["save-id"] is not None:
        g["window"].after_cancel(panel["save-id"])
    panel["save-id"] = g["window"].after(60000, lambda: handle_when_drawing_save_timer_expires(panel))
    render_strokes(panel)


def handle_when_drawing_save_timer_expires(panel):
    panel["save-id"] = None
    if panel["active"]:
        g["send"]({"type": "SAVE_IMAGE", "panel-id": panel["id"]})


def flush_strokes():
    for panel in panels.values():
        finish_stroke(panel)


def render_strokes(panel):
    canvas, photo = panel["canvas"], panel["photo"]
    canvas.delete("image-ink")
    if photo is None:
        return
    width, height = photo.width(), photo.height()
    left, top = (canvas.winfo_width() - width) / 2, (canvas.winfo_height() - height) / 2
    strokes = panel["strokes"] + ([panel["stroke"]] if panel["stroke"] else [])
    for stroke in strokes:
        points = [(left + x * width, top + y * height) for x, y in stroke["points"]]
        thickness = stroke["width"] * min(width, height)
        if len(points) == 1:
            x, y = points[0]
            radius = thickness / 2
            canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=stroke["color"], outline="", tags="image-ink")
        else:
            canvas.create_line(*[value for point in points for value in point], fill=stroke["color"], width=thickness,
                               capstyle="round", joinstyle="round", tags="image-ink")
