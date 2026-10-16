"""Tk workspace framing: tabs, scrollable rows, slots, and geometry controls."""

import tkinter as tk
from tkinter import simpledialog, ttk

from .theme import COLORS

from . import workspace

g = {"window": None, "send": None, "flush": None, "build-panel": None,
     "clear-panels": None, "document": None, "signature": None,
     "projecting": False, "selected-tab": None, "generation": 0}
widgets = {}
pages = {}
rows = {}
slots = {}
PANEL_CREATION_CHOICES = (
    {"label": "[+ Notes]", "event": {"type": "CREATE_NOTES"}},
    {"label": "[+ Image]", "event": {"type": "CREATE_IMAGE"}},
)


def initialize_framing(context):
    g.update(context)
    g.update({"document": None, "signature": None, "projecting": False,
              "selected-tab": None, "generation": 0})
    for collection in (widgets, pages, rows, slots):
        collection.clear()
    parent = context["parent"]
    toolbar = ttk.Frame(parent, padding=(6, 4))
    toolbar.pack(fill="x")
    for label, handler in (("+ Tab", handle_when_user_creates_tab),
                           ("Rename tab", handle_when_user_renames_tab),
                           ("Remove tab", handle_when_user_removes_tab)):
        ttk.Button(toolbar, text=label, command=handler).pack(side="left", padx=(0, 6))
    ttk.Label(toolbar, text="Choose panels in each slot · drag column dividers and row edges").pack(side="left", padx=8)
    notebook = ttk.Notebook(parent)
    notebook.pack(fill="both", expand=True)
    notebook.bind("<<NotebookTabChanged>>", handle_when_user_selects_tab)
    notebook.bind("<Double-Button-1>", handle_when_user_double_clicks_tab)
    widgets["notebook"] = notebook
    context["window"].bind("<MouseWheel>", handle_when_user_scrolls_workspace)


def request(event):
    if not g["projecting"] and g["document"] is not None and g["flush"]():
        g["send"](event)


def handle_when_user_creates_tab():
    label = simpledialog.askstring("New tab", "Tab name:", parent=g["window"])
    if label and label.strip():
        request({"type": "CREATE_TAB", "label": label.strip()})


def handle_when_user_renames_tab():
    if g["document"] is None:
        return
    tab = workspace.get_tab(g["document"], g["selected-tab"])
    label = simpledialog.askstring("Rename tab", "Tab name:", initialvalue=tab["label"], parent=g["window"])
    if label:
        request({"type": "RENAME_TAB", "tab-id": tab["id"], "label": label})


def handle_when_user_double_clicks_tab(event):
    if widgets["notebook"].identify(event.x, event.y) == "label":
        handle_when_user_renames_tab()


def handle_when_user_removes_tab():
    request({"type": "DELETE_TAB", "tab-id": g["selected-tab"]})


def handle_when_user_adds_row():
    request({"type": "ADD_ROW", "tab-id": g["selected-tab"]})


def handle_when_user_selects_tab(event):
    if g["projecting"] or g["document"] is None:
        return
    selected = widgets["notebook"].select()
    tab_id = next((key for key, page in pages.items() if str(page["page"]) == selected), None)
    if tab_id and tab_id != g["selected-tab"]:
        if g["flush"]():
            g["send"]({"type": "SELECT_TAB", "tab-id": tab_id})
        else:
            widgets["notebook"].select(pages[g["selected-tab"]]["page"])


def get_structure_signature(document):
    tab = workspace.get_tab(document, document["selected-tab-id"])
    return (
        tuple((item["id"], item["label"]) for item in document["tabs"]), tab["id"],
        tuple((row_id, document["rows"][row_id]["column-count"],
               tuple(document["positions"][workspace.position_id(row_id, column)]["panel-id"]
                     for column in range(1, document["rows"][row_id]["column-count"] + 1)))
              for row_id in tab["row-ids"]),
        tuple((key, panel["label"]) for key, panel in document["panels"].items()),
    )


def project_workspace(document):
    """Reconcile structural changes; ordinary edits keep their widgets alive."""
    signature = get_structure_signature(document)
    g["document"] = document
    g["projecting"] = True
    try:
        notebook = widgets["notebook"]
        current_ids = {tab["id"] for tab in document["tabs"]}
        for tab_id in list(pages):
            if tab_id not in current_ids:
                pages.pop(tab_id)["page"].destroy()
        for tab in document["tabs"]:
            if tab["id"] not in pages:
                build_tab_page(tab)
            notebook.tab(pages[tab["id"]]["page"], text=tab["label"])
        g["selected-tab"] = document["selected-tab-id"]
        notebook.select(pages[g["selected-tab"]]["page"])
        if signature != g["signature"]:
            g["generation"] += 1
            cancel_column_restorations()
            # Inactive pages are empty. Only one copy of each project instrument is live.
            for page in pages.values():
                for child in page["body"].winfo_children():
                    child.destroy()
            g["clear-panels"]()
            rows.clear()
            slots.clear()
            build_selected_tab_rows()
            g["signature"] = signature
            generation = g["generation"]
            g["window"].after_idle(lambda: restore_workspace_geometry(generation))
        else:
            for row_id, live in rows.items():
                record = document["rows"][row_id]
                if live["height"] != record["height"]:
                    live["frame"].configure(height=record["height"])
                    live["height"] = record["height"]
                if live["proportions"] != record["sash-proportions"]:
                    live["proportions"] = list(record["sash-proportions"])
                    schedule_column_restoration(row_id)
    finally:
        g["projecting"] = False


def build_tab_page(tab):
    page = ttk.Frame(widgets["notebook"])
    page.columnconfigure(0, weight=1)
    page.rowconfigure(0, weight=1)
    canvas = tk.Canvas(page, background=COLORS["app"], highlightthickness=0, yscrollincrement=24)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar = ttk.Scrollbar(page, orient="vertical",
                              command=lambda *args: handle_when_scrollbar_moves_tab(tab["id"], args))
    scrollbar.grid(row=0, column=1, sticky="ns")
    canvas.configure(yscrollcommand=scrollbar.set)
    body = tk.Frame(canvas, background=COLORS["app"], padx=6, pady=6)
    window_id = canvas.create_window(0, 0, window=body, anchor="nw")
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
    body.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
    pages[tab["id"]] = {"page": page, "canvas": canvas, "body": body}
    widgets["notebook"].add(page, text=tab["label"])


def build_selected_tab_rows():
    document = g["document"]
    tab = workspace.get_tab(document, g["selected-tab"])
    body = pages[tab["id"]]["body"]
    for row_id in tab["row-ids"]:
        record = document["rows"][row_id]
        frame = tk.Frame(body, height=record["height"], background=COLORS["app"])
        frame.pack(fill="x")
        frame.grid_propagate(False)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)
        rail = ttk.Frame(frame, width=42)
        rail.grid(row=0, column=0, sticky="ns", padx=(0, 4))
        for label, event in (
            ("↑", {"type": "MOVE_ROW", "row-id": row_id, "direction": -1}),
            *((f"x{count}", {"type": "SET_ROW_COLUMNS", "row-id": row_id, "column-count": count}) for count in (1, 2, 3)),
            ("↓", {"type": "MOVE_ROW", "row-id": row_id, "direction": 1}),
            ("×", {"type": "DELETE_ROW", "row-id": row_id}),
        ):
            button = ttk.Button(rail, text=label, width=3, command=lambda event=event: request(event))
            button.pack(pady=1)
            if label == f"x{record['column-count']}":
                button.state(["disabled"])
        pane = ttk.Panedwindow(frame, orient="horizontal")
        pane.grid(row=0, column=1, sticky="nsew")
        pane.bind("<ButtonPress-1>", lambda event, row_id=row_id: handle_when_column_drag_starts(event, row_id))
        pane.bind("<ButtonRelease-1>", lambda event, row_id=row_id: handle_when_user_releases_column_divider(row_id))
        rows[row_id] = {"frame": frame, "pane": pane, "last-width": None,
                        "height": record["height"], "proportions": list(record["sash-proportions"]),
                        "restore-id": None, "restored-layout": None, "dragging": False}
        pane.bind("<Configure>", lambda event, row_id=row_id: schedule_column_restoration(row_id))
        pane.bind("<Map>", lambda event, row_id=row_id: schedule_column_restoration(row_id))
        for column in range(1, record["column-count"] + 1):
            target = workspace.position_id(row_id, column)
            host = ttk.Frame(pane)
            host.bind("<Configure>", lambda event, row_id=row_id: schedule_column_restoration(row_id))
            pane.add(host, weight=1)
            slots[target] = {"host": host, "panel-id": document["positions"][target]["panel-id"]}
            build_position_host(target)
        build_row_resize_handle(body, row_id)
    ttk.Button(body, text="+ Add row", command=handle_when_user_adds_row).pack(anchor="w", pady=8)


def build_position_host(target):
    document = g["document"]
    position = slots[target]
    host = position["host"]
    panel_id = position["panel-id"]
    if panel_id:
        content = ttk.Frame(host)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        title_row = g["build-panel"]({"parent": content, "panel": document["panels"][panel_id]})
        button = ttk.Button(title_row, text="×", width=2,
                            command=lambda: request({"type": "UNHOST_PANEL", "position-id": target}))
        button.pack(side="right", before=title_row.pack_slaves()[0], padx=(6, 0))
        button.bind("<Control-Button-1>", lambda event: handle_when_user_control_clicks_panel_delete(event, panel_id))
        button.bind("<Control-ButtonRelease-1>", lambda event: "break")
        position["unhost-button"] = button
        return
    header = ttk.Frame(host, padding=(4, 3))
    header.pack(fill="x")
    hosted = workspace.get_hosted_panel_ids(document, g["selected-tab"])
    available = [key for key in document["panels"] if key not in hosted or key == panel_id]
    choices = [{"label": f"{document['panels'][key]['type'].title()}: {document['panels'][key]['label']} ({key[:8]})",
                "event": {"type": "HOST_PANEL", "panel-id": key}} for key in available]
    choices.extend(PANEL_CREATION_CHOICES)
    choices.extend({"label": f"[+ {workspace.get_panel_label(kind)}]", "event": {"type": "CREATE_PROJECT_PANEL", "panel-type": kind}}
                   for key, kind in workspace.PROJECT_PANELS.items() if key not in document["panels"])
    selector = ttk.Combobox(header, values=[choice["label"] for choice in choices], state="readonly", width=24)
    selector.pack(side="left", fill="x", expand=True)
    selector.set("Choose a panel…")
    selector.bind("<<ComboboxSelected>>", lambda event: handle_when_user_selects_slot_choice(target))
    ttk.Label(host, text="Empty slot\nChoose a project panel or create independent Notes.",
              anchor="center", justify="center", wraplength=230).pack(fill="both", expand=True, padx=10, pady=10)
    position["selector"] = selector
    position["available-panel-ids"] = available
    position["choices"] = choices


def handle_when_user_selects_slot_choice(target):
    position = slots.get(target)
    if position is None:
        return
    index = position["selector"].current()
    if index >= 0:
        request({**position["choices"][index]["event"], "position-id": target})


def handle_when_user_control_clicks_panel_delete(event, panel_id):
    """Delete the record and every hosting reference; suppress ordinary button activation."""
    request({"type": "DELETE_PANEL", "panel-id": panel_id})
    return "break"


def cancel_column_restorations():
    for live in rows.values():
        if live["restore-id"] is not None:
            g["window"].after_cancel(live["restore-id"])
            live["restore-id"] = None


def schedule_column_restoration(row_id):
    live = rows.get(row_id)
    if live is not None and not live["dragging"] and live["restore-id"] is None:
        live["restore-id"] = g["window"].after_idle(lambda: apply_column_proportions(row_id))


def apply_column_proportions(row_id):
    if row_id not in rows or row_id not in g["document"]["rows"]:
        return
    widgets_for_row = rows[row_id]
    widgets_for_row["restore-id"] = None
    pane = widgets_for_row["pane"]
    width = pane.winfo_width()
    if width <= 1 or not pane.winfo_ismapped() or widgets_for_row["dragging"]:
        return
    proportions = tuple(widgets_for_row["proportions"])
    actual = tuple(pane.sashpos(index) for index in range(len(proportions)))
    if (width, proportions, actual) == widgets_for_row["restored-layout"]:
        return
    widgets_for_row["last-width"] = width
    # A second pass handles x3 dividers moving past their previous neighbors.
    for unused in range(2):
        for index, fraction in enumerate(proportions):
            pane.sashpos(index, round(width * fraction))
    # Remember the achieved layout too: nested widget requests can change sashes
    # without changing the outer width. Clamped dividers must not cause an idle loop.
    actual = tuple(pane.sashpos(index) for index in range(len(proportions)))
    widgets_for_row["restored-layout"] = (width, proportions, actual)


def restore_workspace_geometry(generation):
    if generation != g["generation"]:
        return
    for row_id in rows:
        schedule_column_restoration(row_id)
    tab = workspace.get_tab(g["document"], g["selected-tab"])
    pages[tab["id"]]["canvas"].yview_moveto(tab.get("scroll-position", 0))


def handle_when_column_drag_starts(event, row_id):
    live = rows.get(row_id)
    if live is not None:
        live["dragging"] = live["pane"].identify(event.x, event.y) != ""


def handle_when_user_releases_column_divider(row_id):
    if row_id not in rows:
        return
    pane = rows[row_id]["pane"]
    count = g["document"]["rows"][row_id]["column-count"]
    width = pane.winfo_width()
    if width > 1 and count > 1:
        proportions = [pane.sashpos(index) / width for index in range(count - 1)]
        rows[row_id]["proportions"] = proportions
        request({"type": "SET_SASH_PROPORTIONS", "row-id": row_id, "proportions": proportions})
    rows[row_id]["dragging"] = False
    schedule_column_restoration(row_id)


def build_row_resize_handle(parent, row_id):
    handle = tk.Frame(parent, height=7, background=COLORS["divider"], cursor="sb_v_double_arrow")
    handle.pack(fill="x", pady=(2, 5))
    drag = {"y": None, "height": None}

    def handle_when_row_drag_starts(event):
        drag.update({"y": event.y_root, "height": rows[row_id]["frame"].winfo_height()})

    def handle_when_row_drag_moves(event):
        if drag["y"] is not None:
            rows[row_id]["frame"].configure(height=max(120, min(10000, drag["height"] + event.y_root - drag["y"])))

    def handle_when_row_drag_ends(event):
        if drag["y"] is not None:
            request({"type": "SET_ROW_HEIGHT", "row-id": row_id, "height": rows[row_id]["frame"].winfo_height()})
            drag["y"] = None

    handle.bind("<ButtonPress-1>", handle_when_row_drag_starts)
    handle.bind("<B1-Motion>", handle_when_row_drag_moves)
    handle.bind("<ButtonRelease-1>", handle_when_row_drag_ends)
    rows[row_id]["resize-handle"] = handle


def handle_when_scrollbar_moves_tab(tab_id, args):
    pages[tab_id]["canvas"].yview(*args)
    request({"type": "SET_TAB_SCROLL", "tab-id": tab_id, "fraction": pages[tab_id]["canvas"].yview()[0]})


def handle_when_user_scrolls_workspace(event):
    if g["document"] is None or event.widget.winfo_class() in {"Text", "Treeview", "TCombobox"}:
        return
    canvas = pages[g["selected-tab"]]["canvas"]
    canvas.yview_scroll(-int(event.delta / 120), "units")
    request({"type": "SET_TAB_SCROLL", "tab-id": g["selected-tab"], "fraction": canvas.yview()[0]})
    return "break"
