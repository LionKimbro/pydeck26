"""Tk-owned Git selections, commit draft, context menus, and text viewers."""

import tkinter as tk
from tkinter import messagebox, ttk

from .theme import COLORS

g = {"send": None, "window": None, "is-closing": None, "message-var": None,
     "state": None, "poll-id": None, "dismissed-message": None}
panels = {}  # Active hosts only; rebuilding a layout retains the commit draft.


def initialize_context(context):
    if g["poll-id"] is not None:
        try:
            g["window"].after_cancel(g["poll-id"])
        except tk.TclError:
            pass
    panels.clear()
    g.update(context)
    g.update({"state": {"snapshot": None, "busy": False, "revision": 0, "message": "Opening repository…"},
              "message-var": tk.StringVar(master=g["window"]), "poll-id": None, "dismissed-message": None})
    g["message-var"].trace_add("write", handle_when_commit_message_changes)
    g["poll-id"] = g["window"].after(5000, handle_when_repository_poll_is_due)


def clear_panels():
    panels.clear()


def send_operation(operation, details=None):
    if g["is-closing"]() or g["state"]["busy"]:
        return
    g["send"]({"type": "GIT_REQUEST", "operation": operation,
               "revision": g["state"]["revision"], **(details or {})})


def handle_when_repository_poll_is_due():
    g["poll-id"] = None
    if g["is-closing"]():
        return
    if panels:
        send_operation("status")
    g["poll-id"] = g["window"].after(5000, handle_when_repository_poll_is_due)


def build_panel(details):
    parent = details["parent"]
    header = tk.Frame(parent, background=COLORS["panel"])
    header.grid(row=0, column=0, sticky="ew", padx=8, pady=6)
    tk.Label(header, text="GIT", foreground=COLORS["accent"], background=COLORS["panel"],
             font=("TkDefaultFont", 12, "bold")).pack(side="left")
    refresh = ttk.Button(header, text="Refresh", command=lambda: send_operation("refresh"))
    refresh.pack(side="right", padx=4)
    push = ttk.Button(header, text="↑ Push", command=lambda: send_operation("push"))
    push.pack(side="right")
    dot = tk.Label(header, text="●", foreground=COLORS["muted"], background=COLORS["panel"])
    dot.pack(side="right", padx=4)
    branch = tk.Label(header, foreground=COLORS["accent"], background=COLORS["panel"])
    branch.pack(side="right")
    columns = ttk.Frame(parent)
    columns.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
    columns.rowconfigure(0, weight=1)
    parent.rowconfigure(0, weight=0)
    parent.rowconfigure(2, weight=1)
    parent.columnconfigure(0, weight=1)
    panel = {"id": details["panel"]["id"], "parent": parent, "branch": branch,
             "refresh": refresh, "push": push, "dot": dot, "lists": {}, "buttons": {}}
    panels[panel["id"]] = panel
    for number, side in enumerate(("staged", "unstaged")):
        columns.columnconfigure(number, weight=1, uniform="git-columns", minsize=60)
        frame = ttk.Frame(columns, padding=(0 if number == 0 else 5, 0, 5 if number == 0 else 0, 0))
        frame.grid(row=0, column=number, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)
        title = "Files Staged for Commit" if side == "staged" else "Files Not Yet Staged"
        title_label = ttk.Label(frame, text=title)
        title_label.grid(row=0, column=0, sticky="w")
        all_var = tk.BooleanVar(master=parent)
        select_all = ttk.Checkbutton(frame, text="Select all", variable=all_var,
                                     command=lambda value=side: handle_when_select_all_clicked(panel, value))
        select_all.grid(row=1, column=0, sticky="w")
        tree = ttk.Treeview(frame, columns=("status", "path", "size", "diff"), selectmode="browse", height=6)
        tree.heading("#0", text="☐")
        tree.column("#0", width=32, minwidth=32, stretch=False)
        tree.heading("status", text="Status")
        tree.column("status", width=88, minwidth=65, stretch=False)
        tree.heading("path", text="File")
        tree.column("path", width=140, minwidth=100)
        tree.heading("size", text="File size")
        tree.column("size", width=80, minwidth=70, stretch=False, anchor="e")
        tree.heading("diff", text="Diff (+/− lines)")
        tree.column("diff", width=110, minwidth=95, stretch=False, anchor="e")
        tree.grid(row=2, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        vertical.grid(row=2, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        horizontal.grid(row=3, column=0, sticky="ew")
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        listing = {"tree": tree, "checked": set(), "records": {}, "all-var": all_var,
                   "select-all": select_all, "signature": None, "title": title_label,
                   "menu": tk.Menu(tree, tearoff=False)}
        panel["lists"][side] = listing
        tree.bind("<Button-1>", lambda event, value=side: handle_when_file_clicked(event, (panel, value)))
        tree.bind("<space>", lambda event, value=side: handle_when_space_pressed(panel, value))
        tree.bind("<Button-3>", lambda event, value=side: handle_when_file_menu_requested(event, (panel, value)))
        tree.heading("#0", command=lambda value=side: toggle_all_from_heading(panel, value))
        actions = ttk.Frame(frame)
        actions.grid(row=4, column=0, sticky="ew", pady=(4, 0))
        choices = (("Unstage", "unstage"), ("Discard", "discard"), ("Commit Staged", "commit")) if side == "staged" else (("Stage", "stage"), ("Revert/Delete", "revert"))
        for label, operation in choices:
            button = ttk.Button(actions, text=label,
                                command=lambda op=operation, value=side: handle_when_action_clicked(panel, {"operation": op, "side": value}))
            panel["buttons"][operation] = button
    caption = ttk.Label(parent, text="Commit message · Commit Staged includes all staged changes")
    caption.grid(row=3, column=0, sticky="w", padx=8)
    panel["commit-caption"] = caption
    entry = ttk.Entry(parent, textvariable=g["message-var"])
    entry.grid(row=4, column=0, sticky="ew", padx=8, pady=(2, 4))
    panel["message"] = entry
    output = ttk.Frame(parent)
    output.grid(row=5, column=0, sticky="ew", padx=8, pady=(0, 5))
    output.columnconfigure(0, weight=1)
    status = ttk.Label(output, anchor="w", justify="left")
    status.grid(row=0, column=0, sticky="ew")
    dismiss = ttk.Button(output, text="Dismiss", command=handle_when_output_dismissed)
    dismiss.grid(row=0, column=1, sticky="ne", padx=(8, 0))
    panel["status"] = status
    panel["output"] = output
    panel["dismiss"] = dismiss
    parent.bind("<Configure>", lambda event: handle_when_panel_resizes(panel))
    project_panel(panel)
    parent.after_idle(lambda: send_operation("status") if panel["id"] in panels else None)
    return header


def handle_when_panel_resizes(panel):
    width = max(80, panel["parent"].winfo_width() - 20)
    panel["status"].configure(wraplength=max(60, width - panel["dismiss"].winfo_reqwidth() - 8))
    panel["commit-caption"].configure(wraplength=width)
    for listing in panel["lists"].values():
        listing["title"].configure(wraplength=max(60, width // 2 - 12))
    for side, operations in (("staged", ("unstage", "discard", "commit")), ("unstaged", ("stage", "revert"))):
        for index, operation in enumerate(operations):
            button = panel["buttons"][operation]
            if width < 640:
                button.grid(row=index, column=0, columnspan=1, sticky="ew", pady=1)
            else:
                button.grid(row=0, column=index, columnspan=1, sticky="w", padx=(0, 3))


def project_git_state(command):
    if (command["message"] != g["state"]["message"]
            or command.get("operation") not in (None, "status")):
        g["dismissed-message"] = None
    g["state"] = command
    if command.get("ok") and command.get("operation") == "commit":
        if g["message-var"].get().strip() == (command.get("committed-message") or "").strip():
            g["message-var"].set("")
    for panel in panels.values():
        project_panel(panel)
    if command.get("viewer") and panels:
        show_text_viewer(command["viewer"])
    if command.get("ok") is False and command.get("operation") in {"file", "diff", "open"} and panels:
        messagebox.showinfo("Git file viewer", command["message"], parent=g["window"])


def project_panel(panel):
    state = g["state"]
    snapshot = state["snapshot"]
    busy = state["busy"]
    project_output(panel)
    panel["refresh"].state(["disabled" if busy else "!disabled"])
    if snapshot is None:
        panel["branch"].configure(text="")
        color, can_push = COLORS["muted"], False
    else:
        ahead, behind = snapshot["ahead"], snapshot["behind"]
        if not snapshot["upstream"]:
            color = COLORS["muted"]
        elif behind:
            color = COLORS["danger"]
        elif ahead:
            color = COLORS["warning"]
        else:
            color = COLORS["accent"]
        can_push = bool(snapshot["upstream"] and ahead and not behind)
        panel["branch"].configure(text=snapshot["branch"])
    panel["dot"].configure(foreground=color)
    panel["push"].state(["!disabled" if can_push and not busy else "disabled"])
    for side, listing in panel["lists"].items():
        records = snapshot[side] if snapshot else []
        signature = tuple(tuple(record.items()) for record in records)
        if signature != listing["signature"]:
            selected_paths = {listing["records"][iid]["path"] for iid in listing["tree"].selection() if iid in listing["records"]}
            listing["checked"].intersection_update(record["path"] for record in records)
            tree = listing["tree"]
            scroll = tree.yview()
            tree.delete(*tree.get_children())
            listing["records"].clear()
            for index, record in enumerate(records):
                iid = str(index)
                listing["records"][iid] = record
                label = f"{record['old-path']} → {record['path']}" if record["old-path"] else record["path"]
                tree.insert("", "end", iid=iid, text="☑" if record["path"] in listing["checked"] else "☐",
                            values=(f"{record['code']} {record['label']}", label,
                                    format_file_size(record.get("size-bytes")), format_diff_size(record.get("diff"))))
                if record["path"] in selected_paths:
                    tree.selection_set(iid)
            if scroll:
                tree.yview_moveto(scroll[0])
            listing["signature"] = signature
        listing["select-all"].state(["disabled" if busy or not records else "!disabled"])
    update_action_buttons(panel)


def project_output(panel):
    message = g["state"]["message"]
    if message and message != g["dismissed-message"]:
        panel["status"].configure(text=message)
        panel["output"].grid()
    else:
        panel["status"].configure(text="")
        panel["output"].grid_remove()


def handle_when_output_dismissed():
    g["dismissed-message"] = g["state"]["message"]
    for panel in panels.values():
        project_output(panel)


def update_action_buttons(panel):
    state = g["state"]
    for side, listing in panel["lists"].items():
        listing["all-var"].set(bool(listing["records"]) and len(listing["checked"]) == len(listing["records"]))
        for operation in (("unstage", "discard") if side == "staged" else ("stage", "revert")):
            panel["buttons"][operation].state(["!disabled" if listing["checked"] and not state["busy"] else "disabled"])
    can_commit = state["snapshot"] and state["snapshot"]["staged"] and g["message-var"].get().strip() and not state["busy"]
    panel["buttons"]["commit"].state(["!disabled" if can_commit else "disabled"])


def format_file_size(size):
    if size is None:
        return "—"
    value = size
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


def format_diff_size(change):
    if change is None:
        return "—"
    if change["binary"]:
        return "Binary"
    return f"+{change['added']:,} −{change['removed']:,}"


def handle_when_commit_message_changes(*unused):
    for panel in panels.values():
        update_action_buttons(panel)


def toggle_file(panel, selection):
    if g["state"]["busy"]:
        return
    side, iid = selection
    listing = panel["lists"][side]
    record = listing["records"].get(iid)
    if record is None:
        return
    path = record["path"]
    if path in listing["checked"]:
        listing["checked"].remove(path)
    else:
        listing["checked"].add(path)
    listing["tree"].item(iid, text="☑" if path in listing["checked"] else "☐")
    update_action_buttons(panel)


def handle_when_file_clicked(event, host):
    panel, side = host
    tree = panel["lists"][side]["tree"]
    if tree.identify_region(event.x, event.y) in {"tree", "cell"}:
        toggle_file(panel, (side, tree.identify_row(event.y)))


def handle_when_space_pressed(panel, side):
    tree = panel["lists"][side]["tree"]
    for iid in tree.selection():
        toggle_file(panel, (side, iid))
    return "break"


def toggle_all_from_heading(panel, side):
    listing = panel["lists"][side]
    listing["all-var"].set(not listing["all-var"].get())
    handle_when_select_all_clicked(panel, side)


def handle_when_select_all_clicked(panel, side):
    if g["state"]["busy"]:
        return
    listing = panel["lists"][side]
    listing["checked"].clear()
    if listing["all-var"].get():
        listing["checked"].update(record["path"] for record in listing["records"].values())
    for iid, record in listing["records"].items():
        listing["tree"].item(iid, text="☑" if record["path"] in listing["checked"] else "☐")
    update_action_buttons(panel)


def handle_when_action_clicked(panel, action):
    operation, side = action["operation"], action["side"]
    revision = g["state"]["revision"]
    listing = panel["lists"][side]
    paths = [record["path"] for record in listing["records"].values() if record["path"] in listing["checked"]]
    if operation in {"revert", "discard"}:
        explanation = ("Revert these files to the last commit, discarding ALL staged and unstaged changes? Files with no committed version will be deleted."
                       if operation == "revert" else "Discard ALL staged and unstaged changes to these files? They will match the last commit. Newly added files will be deleted.")
        if not messagebox.askyesno("Revert/Delete" if operation == "revert" else operation.title(), explanation + "\n\n" + "\n".join(paths), parent=g["window"]):
            return
    send_operation(operation, {"side": side, "paths": paths, "message": g["message-var"].get(), "revision": revision})


def handle_when_file_menu_requested(event, host):
    panel, side = host
    tree = panel["lists"][side]["tree"]
    iid = tree.identify_row(event.y)
    if iid not in panel["lists"][side]["records"] or g["state"]["busy"]:
        return
    tree.selection_set(iid)
    record = panel["lists"][side]["records"][iid]
    revision = g["state"]["revision"]
    menu = panel["lists"][side]["menu"]
    menu.delete(0, "end")
    for label, operation in (("View File", "file"), ("View Diff", "diff"), ("Open File", "open")):
        menu.add_command(label=label, command=lambda op=operation: send_operation(op, {"side": side, "paths": [record["path"]], "revision": revision}))
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()
    return "break"


def show_text_viewer(viewer):
    window = tk.Toplevel(g["window"])
    window.title(viewer["title"])
    window.geometry("900x600")
    window.rowconfigure(0, weight=1)
    window.columnconfigure(0, weight=1)
    text = tk.Text(window, wrap="none", font=("TkFixedFont", 11), padx=8, pady=8)
    text.grid(row=0, column=0, sticky="nsew")
    vertical = ttk.Scrollbar(window, orient="vertical", command=text.yview)
    vertical.grid(row=0, column=1, sticky="ns")
    horizontal = ttk.Scrollbar(window, orient="horizontal", command=text.xview)
    horizontal.grid(row=1, column=0, sticky="ew")
    text.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    text.insert("1.0", viewer["text"])
    text.configure(state="disabled")
    window.bind("<Escape>", lambda event: window.destroy())
