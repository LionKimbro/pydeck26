"""Captain's Log presentation, minute clock, and unsaved drafts, owned by Tk."""

from copy import deepcopy
from datetime import datetime
import tkinter as tk
from tkinter import font, ttk
from uuid import uuid4

from . import captains_log
from .theme import COLORS

g = {"send": None, "window": None, "is-closing": None, "selected": "new",
     "projecting": False, "initialized": False, "clock-id": None}
widgets = {}  # At most one active host per tab.
drafts = {}  # GUID or 'new' -> fields and their saved baseline; retained across layout changes.
pending = {}  # Request ID -> originating draft and exact submitted fields.
entries = {}  # Independent durable entry presentation, never canonical records.
control_keys = set()


def empty_fields():
    return {"hook": "", "tags": "", "major": False, "body": ""}


def initialize_context(context):
    if g["clock-id"] is not None:
        try:
            g["window"].after_cancel(g["clock-id"])
        except tk.TclError:
            pass
    for collection in (widgets, drafts, pending, entries, control_keys):
        collection.clear()
    g.update(context)
    g.update({"selected": "new", "projecting": False, "initialized": False, "clock-id": None})
    window = g["window"]
    for key in ("Control_L", "Control_R"):
        window.bind(f"<KeyPress-{key}>", handle_when_control_pressed, add="+")
        window.bind(f"<KeyRelease-{key}>", handle_when_control_released, add="+")
    window.bind("<FocusOut>", handle_when_focus_leaves_window, add="+")
    schedule_clock()


def clear_panels():
    widgets.clear()  # Drafts have already been captured before framing reconciliation.


def get_draft(key):
    if key not in drafts:
        fields = captains_log.get_fields(entries[key]) if key != "new" else empty_fields()
        drafts[key] = {"fields": deepcopy(fields), "baseline": deepcopy(fields),
                       "expected": deepcopy(entries.get(key)), "error": ""}
    return drafts[key]


def is_dirty(key):
    draft = drafts.get(key)
    return draft is not None and draft["fields"] != draft["baseline"]


def build_panel(details):
    parent = details["parent"]
    parent.rowconfigure(0, weight=0)
    parent.rowconfigure(1, weight=1)
    header = ttk.Frame(parent, padding=(8, 6))
    header.grid(row=0, column=0, sticky="ew")
    ttk.Label(header, text="CAPTAIN'S LOG", foreground=COLORS["accent"],
              font=("TkDefaultFont", 12, "bold")).pack(side="left")
    pane = ttk.Panedwindow(parent, orient="horizontal")
    pane.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
    left = ttk.Frame(pane, width=330)
    right = ttk.Frame(pane, padding=(8, 0, 0, 0))
    pane.add(left, weight=2)
    pane.add(right, weight=3)
    left.rowconfigure(0, weight=1)
    left.columnconfigure(0, weight=1)
    # A separate style keeps item colors visible even while their row is selected.
    style = ttk.Style(parent)
    for name, base in (("CaptainLog", "Treeview"), ("CaptainLog.Heading", "Treeview.Heading")):
        style.layout(name, style.layout(base))
        style.configure(name, **style.configure(base))
        style.map(name, **{key: value for key, value in style.map(base).items() if key != "foreground"})
    tree = ttk.Treeview(left, style="CaptainLog", columns=("date", "time", "hook"), show="headings", selectmode="browse", height=6)
    for name, label, width in (("date", "Date", 90), ("time", "Time", 65), ("hook", "Hook", 160)):
        tree.heading(name, text=label)
        tree.column(name, width=width, minwidth=55, stretch=name == "hook")
    tree.grid(row=0, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(left, orient="vertical", command=tree.yview)
    scroll.grid(row=0, column=1, sticky="ns")
    horizontal = ttk.Scrollbar(left, orient="horizontal", command=tree.xview)
    horizontal.grid(row=1, column=0, sticky="ew")
    tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
    major_font = font.nametofont("TkDefaultFont").copy()
    major_font.configure(weight="bold")
    new_font = font.nametofont("TkDefaultFont").copy()
    new_font.configure(slant="italic")
    tree.tag_configure("dirty", foreground=COLORS["danger"])
    tree.tag_configure("major", font=major_font)
    tree.tag_configure("new", foreground=COLORS["accent"], background=COLORS["control"], font=new_font)
    tree.bind("<<TreeviewSelect>>", handle_when_entry_selected)
    right.columnconfigure(0, weight=1)
    right.rowconfigure(7, weight=1)
    stamp = ttk.Label(right)
    stamp.grid(row=0, column=0, sticky="w")
    modified = ttk.Label(right, foreground=COLORS["danger"])
    modified.grid(row=1, column=0, sticky="w")
    ttk.Label(right, text="Hook (optional)").grid(row=2, column=0, sticky="w")
    hook_var = tk.StringVar(master=parent)
    hook = ttk.Entry(right, textvariable=hook_var)
    hook.grid(row=3, column=0, sticky="ew", pady=(0, 3))
    ttk.Label(right, text="Tags (space separated)").grid(row=4, column=0, sticky="w")
    tags_var = tk.StringVar(master=parent)
    tags = ttk.Entry(right, textvariable=tags_var)
    tags.grid(row=5, column=0, sticky="ew", pady=(0, 3))
    major_var = tk.BooleanVar(master=parent)
    major = ttk.Checkbutton(right, text="Major", variable=major_var)
    major.grid(row=6, column=0, sticky="w")
    body_frame = ttk.Frame(right)
    body_frame.grid(row=7, column=0, sticky="nsew", pady=4)
    body_frame.rowconfigure(0, weight=1)
    body_frame.columnconfigure(0, weight=1)
    body = tk.Text(body_frame, wrap="word", undo=True, width=20, height=5, padx=7, pady=7,
                   font=("TkDefaultFont", 11))
    body.grid(row=0, column=0, sticky="nsew")
    body_scroll = ttk.Scrollbar(body_frame, orient="vertical", command=body.yview)
    body_scroll.grid(row=0, column=1, sticky="ns")
    body.configure(yscrollcommand=body_scroll.set)
    actions = ttk.Frame(right)
    actions.grid(row=8, column=0, sticky="ew")
    save = ttk.Button(actions, text="Save", command=handle_when_save_clicked)
    save.pack(side="left")
    save.bind("<Control-Button-1>", handle_when_save_over_clicked)
    save.bind("<Control-ButtonRelease-1>", lambda event: "break")
    ttk.Label(actions, text="Hold Ctrl to Save Over").pack(side="left", padx=6)
    status = ttk.Label(right, wraplength=330)
    status.grid(row=9, column=0, sticky="ew", pady=(3, 0))
    widgets.update({"tree": tree, "body": body, "hook-var": hook_var, "tags-var": tags_var,
                    "major-var": major_var, "save": save, "stamp": stamp, "modified": modified,
                    "status": status, "major-font": major_font, "new-font": new_font})
    for variable in (hook_var, tags_var, major_var):
        variable.trace_add("write", handle_when_fields_change)
    body.bind("<<Modified>>", handle_when_fields_change)
    refresh_rows()
    show_selected_entry()
    return header


def capture_draft():
    if not widgets or g["projecting"] or not widgets["body"].winfo_exists():
        return
    draft = get_draft(g["selected"])
    fields = {"hook": widgets["hook-var"].get(), "tags": widgets["tags-var"].get(),
              "major": widgets["major-var"].get(), "body": widgets["body"].get("1.0", "end-1c")}
    if fields != draft["fields"]:
        draft["fields"] = fields
        draft["error"] = ""
        refresh_rows()
    widgets["body"].edit_modified(False)
    update_save_controls()


def handle_when_fields_change(*unused):
    capture_draft()


def project_entries(records, initialized):
    capture_draft()
    entries.clear()
    entries.update({entry["guid"]: deepcopy(entry) for entry in records})
    g["initialized"] = initialized
    # Live drafts own their fields. Routine projections never refill the editor.
    refresh_rows()


def refresh_rows():
    if not widgets:
        return
    tree = widgets["tree"]
    moment = datetime.now()
    order = ["new"] + [entry["guid"] for entry in sorted(entries.values(), key=lambda item: (item["date"], item["time"]), reverse=True)]
    g["projecting"] = True
    try:
        for iid in tree.get_children():
            if iid not in order:
                tree.delete(iid)
        for index, key in enumerate(order):
            draft = drafts.get(key)
            fields = draft["fields"] if draft else captains_log.get_fields(entries[key]) if key != "new" else empty_fields()
            if key == "new":
                values = (moment.strftime("%Y-%m-%d"), moment.strftime("%H:%M"), "<new entry>")
            else:
                entry = entries[key]
                preview = next((line.strip() for line in fields["body"].splitlines() if line.strip()), "")
                values = (entry["date"], entry["time"], fields["hook"] or preview[:100])
            tags = tuple(tag for tag, active in (("dirty", is_dirty(key)), ("new", key == "new"), ("major", fields["major"])) if active)
            if tree.exists(key):
                tree.item(key, values=values, tags=tags)
                tree.move(key, "", index)
            else:
                tree.insert("", index, iid=key, values=values, tags=tags)
        if g["selected"] not in order:
            g["selected"] = "new"
        if tree.selection() != (g["selected"],):
            tree.selection_set(g["selected"])
    finally:
        g["projecting"] = False
    update_save_controls()


def show_selected_entry(flags=None):
    if not widgets:
        return
    key = g["selected"]
    draft = get_draft(key)
    g["projecting"] = True
    try:
        if "preserve-text" not in (flags or []):
            for field in ("hook", "tags", "major"):
                widgets[f"{field}-var"].set(draft["fields"][field])
            body = widgets["body"]
            body.delete("1.0", "end")
            body.insert("1.0", draft["fields"]["body"])
            body.edit_reset()
            body.edit_modified(False)
        entry = entries.get(key)
        widgets["stamp"].configure(text=f"{entry['date']} {entry['time']}" if entry else "New entry · time is recorded when you Save")
        modified = entry.get("modified-on") if entry else None
        widgets["modified"].configure(text=f"Last edited {modified}" if modified else "")
    finally:
        g["projecting"] = False
    update_save_controls()


def handle_when_entry_selected(event):
    if g["projecting"] or not widgets:
        return
    selection = widgets["tree"].selection()
    if selection and selection[0] != g["selected"]:
        capture_draft()
        g["selected"] = selection[0]
        refresh_rows()
        show_selected_entry()


def update_save_controls():
    if not widgets:
        return
    key = g["selected"]
    busy = any(request["key"] == key for request in pending.values())
    enabled = g["initialized"] and is_dirty(key) and not busy and not g["is-closing"]()
    widgets["save"].configure(text="Save Over" if control_keys and key != "new" else "Save")
    widgets["save"].state(["!disabled" if enabled else "disabled"])
    error = drafts.get(key, {}).get("error")
    widgets["status"].configure(text=error or ("Saving…" if busy else "Unsaved changes" if is_dirty(key) else ""),
                                foreground=COLORS["danger"] if error or is_dirty(key) else COLORS["secondary"])


def handle_when_save_clicked():
    save_draft(["overwrite"] if control_keys else [])


def handle_when_save_over_clicked(event):
    save_draft(["overwrite"])
    return "break"


def save_draft(flags=None):
    capture_draft()
    key = g["selected"]
    if not is_dirty(key) or any(request["key"] == key for request in pending.values()) or g["is-closing"]():
        return
    draft = get_draft(key)
    request_id = str(uuid4())
    pending[request_id] = {"key": key, "fields": deepcopy(draft["fields"])}
    g["send"]({"type": "CAPTAINS_LOG_SAVE", "request-id": request_id,
               "guid": None if key == "new" else key, "expected": deepcopy(draft["expected"]),
               "fields": deepcopy(draft["fields"]), "overwrite": "overwrite" in (flags or [])})
    update_save_controls()


def apply_result(command):
    capture_draft()
    request = pending.pop(command["request-id"], None)
    if request is None:
        return
    key = request["key"]
    draft = get_draft(key)
    if not command["ok"]:
        draft["error"] = command["error"]
        update_save_controls()
        return
    entry = command["entry"]
    if entry is None:  # Same-second creation was ignored; keep its draft intact.
        update_save_controls()
        return
    entries.clear()
    entries.update({record["guid"]: deepcopy(record) for record in command["entries"]})
    new_key = entry["guid"]
    fields = draft["fields"]
    # Normalization performed by Core is accepted only if typing has not moved on.
    if fields == request["fields"]:
        fields = captains_log.get_fields(entry)
    drafts.pop(key, None)
    drafts[new_key] = {"fields": deepcopy(fields), "baseline": captains_log.get_fields(entry),
                       "expected": deepcopy(entry), "error": ""}
    selected = g["selected"] == key
    if selected:
        g["selected"] = new_key
    refresh_rows()
    if selected:
        show_selected_entry(["preserve-text"] if fields == request["fields"] or fields != captains_log.get_fields(entry) else [])


def handle_when_control_pressed(event):
    control_keys.add(event.keysym)
    update_save_controls()


def handle_when_control_released(event):
    control_keys.discard(event.keysym)
    update_save_controls()


def handle_when_focus_leaves_window(event):
    g["window"].after_idle(reset_control_if_unfocused)


def reset_control_if_unfocused():
    if g["window"].winfo_exists() and g["window"].focus_displayof() is None:
        control_keys.clear()
        update_save_controls()


def schedule_clock():
    moment = datetime.now()
    delay = 60000 - (moment.second * 1000 + moment.microsecond // 1000)
    g["clock-id"] = g["window"].after(delay, handle_when_minute_changes)


def handle_when_minute_changes():
    g["clock-id"] = None
    if g["is-closing"]():
        return
    refresh_rows()  # Presentation only: no event or stack goes to Core.
    schedule_clock()
