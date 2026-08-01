"""PyDeck's project-bound masthead and first functional Whiteboard."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk

import lionscliapp as app
from lionscliapp.execroot import get_execroot

from pydeck26.project_snapshot import read_project_snapshot
from pydeck26.storage import (
    format_snapshot_time,
    initialize_project,
    is_initialized,
    list_snapshots,
    load_whiteboard,
    read_snapshot,
    save_snapshot,
    save_whiteboard,
)


g = {
    "project-root": None,
    "snapshot": None,
    "current-text": "",
    "virtual-snapshot": None,
    "history-items": [],
    "view-index": 0,
    "suppress-editor-events": False,
    "status": "Opening PyDeck 26.",
}
widgets = {}


def launch_cockpit() -> None:
    """Open a cockpit permanently bound to the command's project root."""
    g["project-root"] = get_execroot()
    g["snapshot"] = read_project_snapshot(g["project-root"])
    root = tk.Tk()
    root.withdraw()
    app.attach_tk(root, handle_when_lionscliapp_forwards_message)
    realize_main_cockpit_window(root)
    refresh_cockpit_for_bound_project()
    root.mainloop()


def realize_main_cockpit_window(root: tk.Tk) -> None:
    """Build the one visible, resizable cockpit window."""
    window = tk.Toplevel(root)
    window.geometry("1120x760")
    window.minsize(820, 560)
    window.columnconfigure(0, weight=1)
    window.rowconfigure(1, weight=1)
    widgets["window"] = window
    build_masthead(window)
    build_cockpit_surface(window)
    build_status_bar(window)
    window.protocol("WM_DELETE_WINDOW", handle_when_user_closes_main_cockpit)


def build_masthead(window: tk.Toplevel) -> None:
    """Create the project-orientation masthead that remains visible on resize."""
    header = tk.Frame(window, background="#182333", padx=18, pady=14)
    header.grid(row=0, column=0, sticky="ew")
    title = tk.Label(header, background="#182333", foreground="#f4f7fb", font=("TkDefaultFont", 19, "bold"))
    title.pack(anchor="w")
    hook = tk.Label(header, background="#182333", foreground="#b8c7da", font=("TkDefaultFont", 10), wraplength=1040, justify="left")
    hook.pack(anchor="w", pady=(3, 3))
    path = tk.Label(header, background="#182333", foreground="#8fc4f4", cursor="hand2", font=("TkDefaultFont", 9, "underline"))
    path.pack(anchor="w")
    path.bind("<Button-1>", handle_when_user_clicks_project_root_path)
    widgets["title"] = title
    widgets["hook"] = hook
    widgets["project-root-path"] = path


def build_cockpit_surface(window: tk.Toplevel) -> None:
    """Lay out the cockpit framing rooms with the Whiteboard as the live center."""
    surface = tk.Frame(window, background="#e8edf3", padx=16, pady=10)
    surface.grid(row=1, column=0, sticky="nsew")
    surface.columnconfigure(0, weight=1, uniform="cockpit-columns")
    surface.columnconfigure(1, weight=1, uniform="cockpit-columns")
    surface.rowconfigure(0, weight=1)
    surface.rowconfigure(1, weight=1)
    surface.rowconfigure(2, weight=4)
    widgets["cockpit-surface"] = surface
    build_inactive_card({"title": "STRUCTURE", "hint": "folders, packages, paths, jumpers", "row": 0, "column": 0})
    build_inactive_card({"title": "DICTIONARY", "hint": "project identity, editable entry", "row": 0, "column": 1})
    build_inactive_card({"title": "CONVERSATIONS", "hint": "lifeline, register, return paths", "row": 1, "column": 0})
    build_inactive_card({"title": "RESOURCES / JUMPERS", "hint": "tools, documents, and useful places", "row": 1, "column": 1})
    build_whiteboard_card()


def build_inactive_card(card_spec: dict) -> None:
    """Keep a visible, intentionally inactive place for a later cockpit feature."""
    surface = widgets["cockpit-surface"]
    card = tk.Frame(surface, background="#ffffff", highlightbackground="#c7d2df", highlightthickness=1, padx=14, pady=12)
    card.grid(row=card_spec["row"], column=card_spec["column"], sticky="nsew", padx=5, pady=5)
    tk.Label(card, text=card_spec["title"], background="#ffffff", foreground="#173b62", font=("TkDefaultFont", 12, "bold")).pack(anchor="w")
    tk.Label(card, text=card_spec["hint"], background="#ffffff", foreground="#667789", font=("TkDefaultFont", 9)).pack(anchor="w", pady=(1, 10))
    tk.Label(card, text="This room is being held open for the project.", background="#ffffff", foreground="#263746", anchor="nw", justify="left").pack(anchor="w", fill="both", expand=True)


def build_whiteboard_card() -> None:
    """Build the directly editable present and its right-hand historical control."""
    surface = widgets["cockpit-surface"]
    card = tk.Frame(surface, background="#ffffff", highlightbackground="#c7d2df", highlightthickness=1, padx=14, pady=12)
    card.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
    card.columnconfigure(0, weight=1)
    card.rowconfigure(2, weight=1)
    tk.Label(card, text="WHITEBOARD", background="#ffffff", foreground="#173b62", font=("TkDefaultFont", 12, "bold")).grid(row=0, column=0, sticky="w")
    tk.Label(card, text="loose intentional notes, current thinking, and recoverable earlier states", background="#ffffff", foreground="#667789", font=("TkDefaultFont", 9)).grid(row=1, column=0, sticky="w", pady=(1, 8))

    controls = ttk.Frame(card)
    controls.grid(row=0, column=1, rowspan=2, sticky="e")
    ttk.Button(controls, text="Snapshot", command=handle_when_user_saves_snapshot).grid(row=0, column=0)

    editor = tk.Text(card, wrap="word", undo=True, font=("TkFixedFont", 11), padx=10, pady=10, relief="solid", borderwidth=1)
    editor.grid(row=2, column=0, sticky="nsew", padx=(0, 10))
    editor.bind("<<Modified>>", handle_when_whiteboard_text_changes)
    widgets["whiteboard-editor"] = editor

    history = tk.Frame(card, background="#f2f5f8", padx=6, pady=8, width=52)
    history.grid(row=2, column=1, sticky="ns")
    history.grid_propagate(False)
    scale = tk.Scale(history, from_=0, to=0, orient="vertical", resolution=1, showvalue=False, length=245, command=handle_when_snapshot_scale_changes, background="#f2f5f8", highlightthickness=0)
    scale.pack(anchor="center", fill="y", expand=True)
    widgets["snapshot-scale"] = scale

    initialization = tk.Frame(card, background="#fff6d8", padx=10, pady=8)
    tk.Label(initialization, text="PyDeck 26 has not been initialized for this project.", background="#fff6d8", foreground="#654f00").pack(side="left")
    ttk.Button(initialization, text="Initialize PyDeck 26", command=handle_when_user_initializes_project).pack(side="left", padx=(12, 0))
    widgets["initialization-panel"] = initialization


def build_status_bar(window: tk.Toplevel) -> None:
    """Create the persistent status message area."""
    status = ttk.Label(window, anchor="w", relief="sunken", padding=(8, 4))
    status.grid(row=2, column=0, sticky="ew")
    widgets["status"] = status
    project_status()


def refresh_cockpit_for_bound_project() -> None:
    """Project bound-project identity and Whiteboard state into the window."""
    snapshot = g["snapshot"]
    identity = snapshot["identity"]
    root = g["project-root"]
    name = identity.get("name") or root.name
    hook = read_project_hook(root, identity)
    widgets["window"].title(f"PyDeck 26: {name}")
    widgets["title"].configure(text=f"PyDeck 26: {name}")
    widgets["hook"].configure(text=hook or "No project hook has been recorded yet.")
    widgets["project-root-path"].configure(text=str(root))
    if is_initialized(root):
        widgets["initialization-panel"].grid_remove()
        load_current_whiteboard()
        refresh_snapshot_navigation()
        g["status"] = "Current"
    else:
        show_initialization_state()
    project_status()


def read_project_hook(root: Path, identity: dict) -> str:
    """Find a project hook when the local project dictionary exposes one."""
    if isinstance(identity.get("hook"), str):
        return identity["hook"]
    for path in [root / "db" / "project-dictionary.json", root / "db" / "dictionary.json"]:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data.get("hook"), str):
            return data["hook"]
    return ""


def show_initialization_state() -> None:
    """Leave the cockpit useful and clear when no PyDeck-owned data exists."""
    editor = widgets["whiteboard-editor"]
    set_editor_text("Initialize PyDeck 26 to open this project's Whiteboard.\n\nNo unrelated project files will be created or changed.")
    editor.configure(state="disabled")
    widgets["initialization-panel"].grid(row=3, column=0, sticky="ew", pady=(8, 0))
    widgets["snapshot-scale"].configure(to=0, state="disabled")
    g["status"] = "PyDeck 26 has not been initialized for this project."


def handle_when_user_initializes_project() -> None:
    """Run the same idempotent initialization machine as the CLI command."""
    initialize_project(g["project-root"])
    widgets["initialization-panel"].grid_remove()
    widgets["snapshot-scale"].configure(state="normal")
    load_current_whiteboard()
    refresh_snapshot_navigation()
    g["status"] = "Current"
    project_status()


def load_current_whiteboard() -> None:
    """Display the mutable current Whiteboard in editable form."""
    g["current-text"] = load_whiteboard(g["project-root"])
    set_editor_text(g["current-text"])
    widgets["whiteboard-editor"].configure(state="normal")
    g["view-index"] = 0


def refresh_snapshot_navigation() -> None:
    """Build discrete history positions: current, virtual, then disk snapshots."""
    items = []
    if g["virtual-snapshot"] is not None:
        items.append(g["virtual-snapshot"])
    for path in list_snapshots(g["project-root"]):
        items.append({"kind": "snapshot", "path": path})
    g["history-items"] = items
    scale = widgets["snapshot-scale"]
    scale.configure(to=len(items), state="normal")
    scale.set(0)


def handle_when_snapshot_scale_changes(value: str) -> None:
    """Recall current, virtual, or disk history from a discrete scale position."""
    index = int(float(value))
    if index == g["view-index"]:
        return
    if index == 0:
        load_current_whiteboard()
        g["status"] = "Current"
    else:
        show_history_item(index)
    project_status()


def show_history_item(index: int) -> None:
    """Show an editable historical point whose first edit naturally creates a new present."""
    item = g["history-items"][index - 1]
    if item["kind"] == "virtual":
        text = item["text"]
        label = f"Virtual snapshot: from {item['created-at'].strftime('%Y-%m-%d %H:%M:%S')}"
    else:
        text = read_snapshot(item["path"])
        label = f"Snapshot: {format_snapshot_time(item['path'])}"
    set_editor_text(text)
    widgets["whiteboard-editor"].configure(state="normal")
    g["view-index"] = index
    g["status"] = label


def handle_when_user_saves_snapshot() -> None:
    """Capture the current Whiteboard as one immutable timestamped record."""
    if not is_initialized(g["project-root"]):
        g["status"] = "Initialize PyDeck 26 before creating a Whiteboard snapshot."
    elif g["view-index"] != 0:
        g["status"] = "Only Current can be snapshotted."
    else:
        try:
            save_snapshot(g["project-root"], g["current-text"])
        except FileExistsError:
            g["status"] = "A snapshot already exists for this second. Please try again."
        else:
            refresh_snapshot_navigation()
            g["status"] = "Current"
    project_status()


def handle_when_whiteboard_text_changes(event: tk.Event) -> None:
    """Auto-save edits and promote recalled history into a new current Whiteboard."""
    editor = widgets["whiteboard-editor"]
    if g["suppress-editor-events"] or not editor.edit_modified():
        return
    editor.edit_modified(False)
    new_text = get_editor_text()
    if g["view-index"] != 0:
        g["virtual-snapshot"] = {
            "kind": "virtual",
            "text": g["current-text"],
            "created-at": datetime.now(),
        }
        g["view-index"] = 0
        g["current-text"] = new_text
        refresh_snapshot_navigation()
    else:
        g["current-text"] = new_text
    save_whiteboard(g["project-root"], g["current-text"])
    g["status"] = "Current"
    project_status()


def handle_when_user_clicks_project_root_path(event: tk.Event) -> None:
    """Open the bound project root in Windows Explorer."""
    os.startfile(g["project-root"])


def handle_when_lionscliapp_forwards_message(message: dict) -> None:
    """Raise the cockpit when LionsCLIApp forwards a later invocation."""
    if message.get("type") == "summon":
        app.bring_window_to_front(widgets["window"])


def handle_when_user_closes_main_cockpit() -> None:
    """End the Tk runtime when its cockpit window closes."""
    widgets["window"].master.destroy()


def set_editor_text(text: str) -> None:
    """Replace displayed Whiteboard text while temporarily allowing writes."""
    editor = widgets["whiteboard-editor"]
    g["suppress-editor-events"] = True
    editor.configure(state="normal")
    editor.delete("1.0", tk.END)
    editor.insert("1.0", text)
    editor.edit_modified(False)
    g["suppress-editor-events"] = False


def get_editor_text() -> str:
    """Return the Text widget's ordinary text without Tk's trailing sentinel newline."""
    return widgets["whiteboard-editor"].get("1.0", "end-1c")


def project_status() -> None:
    """Project the current runtime status message."""
    widgets["status"].configure(text=g["status"])
