"""PyDeck's project-bound masthead and first functional Whiteboard."""

from __future__ import annotations

import os
import re
import uuid
import webbrowser
from datetime import date, datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk

import lionscliapp as app
from lionscliapp.execroot import get_execroot

from pydeck26 import description_editor
from pydeck26.project_snapshot import read_project_snapshot
from pydeck26.storage import (
    format_snapshot_time,
    initialize_project,
    is_initialized,
    list_snapshots,
    load_whiteboard,
    load_conversations,
    load_dictionary_entry,
    read_snapshot,
    save_snapshot,
    save_conversations,
    save_dictionary_entry,
    save_whiteboard,
)


g = {
    "project-root": None,
    "snapshot": None,
    "current-text": "",
    "virtual-snapshot": None,
    "history-items": [],
    "view-index": 0,
    "is-dirty": False,
    "whiteboard-dirty": False,
    "dictionary-document": {},
    "dictionary-dirty": False,
    "conversations-document": {"items": []},
    "selected-conversation-id": None,
    "conversation-editor-dirty": False,
    "conversations-dirty": False,
    "project-name": "no project entered",
    "project-guid": "",
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
    window.bind_all("<Control-s>", handle_when_user_uses_project_save_shortcut)
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
    title.configure(cursor="hand2")
    title.bind("<Button-1>", handle_when_user_clicks_project_title)
    hook = tk.Label(header, background="#182333", foreground="#b8c7da", font=("TkDefaultFont", 10), wraplength=1040, justify="left")
    hook.pack(anchor="w", pady=(3, 3))
    path_line = tk.Frame(header, background="#182333")
    path_line.pack(anchor="w")
    path = tk.Label(path_line, background="#182333", foreground="#8fc4f4", cursor="hand2", font=("TkDefaultFont", 9, "underline"))
    path.pack(side="left")
    path.bind("<Button-1>", handle_when_user_clicks_project_root_path)
    guid = tk.Label(path_line, background="#182333", foreground="#526273", cursor="hand2", font=("TkDefaultFont", 9))
    guid.pack(side="left", padx=(8, 0))
    guid.bind("<Button-1>", handle_when_user_clicks_project_guid)
    widgets["title"] = title
    widgets["hook"] = hook
    widgets["project-root-path"] = path
    widgets["project-guid"] = guid


def build_cockpit_surface(window: tk.Toplevel) -> None:
    """Lay out the cockpit framing rooms with the Whiteboard as the live center."""
    surface = tk.Frame(window, background="#e8edf3", padx=16, pady=10)
    surface.grid(row=1, column=0, sticky="nsew")
    surface.columnconfigure(0, weight=1, uniform="cockpit-columns")
    surface.columnconfigure(1, weight=1, uniform="cockpit-columns")
    surface.rowconfigure(0, weight=1)
    surface.rowconfigure(1, weight=2)
    surface.rowconfigure(2, weight=0)
    widgets["cockpit-surface"] = surface
    build_inactive_card({"title": "STRUCTURE", "hint": "folders, packages, paths, jumpers", "row": 0, "column": 0})
    build_dictionary_card()
    build_conversations_card()
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


def build_dictionary_card() -> None:
    """Build the compact editable identity surface for the current project dictionary."""
    surface = widgets["cockpit-surface"]
    card = tk.Frame(surface, background="#ffffff", highlightbackground="#c7d2df", highlightthickness=1, padx=10, pady=10)
    card.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
    card.columnconfigure(1, weight=1)
    tk.Label(card, text="DICTIONARY", background="#ffffff", foreground="#173b62", font=("TkDefaultFont", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
    name = build_dictionary_entry(card, "Name", 1)
    title = build_dictionary_entry(card, "Title", 2)
    tags = build_dictionary_entry(card, "Tags", 3)
    hook = build_dictionary_entry(card, "Hook", 4)
    ttk.Button(card, text="Save", width=4, command=handle_when_user_saves_dictionary).grid(row=5, column=0, sticky="w", pady=(6, 0))
    ttk.Button(card, text="Open Full Entry", command=handle_when_user_opens_full_dictionary_entry).grid(row=5, column=1, sticky="e", pady=(6, 0))
    for entry in [name, title, tags, hook]:
        entry.bind("<KeyRelease>", handle_when_dictionary_editor_changes)
    widgets["dictionary-name"] = name
    widgets["dictionary-title"] = title
    widgets["dictionary-tags"] = tags
    widgets["dictionary-hook"] = hook


def build_dictionary_entry(parent: tk.Frame, label: str, row: int) -> ttk.Entry:
    """Create one dense key-and-value dictionary row."""
    ttk.Label(parent, text=label, width=7).grid(row=row, column=0, sticky="w", padx=(0, 6), pady=2)
    entry = ttk.Entry(parent)
    entry.grid(row=row, column=1, sticky="ew", pady=2)
    return entry


def build_conversations_card() -> None:
    """Build a compact master-detail project conversation register."""
    surface = widgets["cockpit-surface"]
    card = tk.Frame(surface, background="#ffffff", highlightbackground="#c7d2df", highlightthickness=1, padx=10, pady=10)
    card.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
    card.columnconfigure(0, weight=2)
    card.columnconfigure(1, weight=3)
    card.rowconfigure(2, weight=0)
    tk.Label(card, text="CONVERSATIONS", background="#ffffff", foreground="#173b62", font=("TkDefaultFont", 12, "bold")).grid(row=0, column=0, sticky="w")
    tk.Label(card, text="conversations with LLMs", background="#ffffff", foreground="#667789", font=("TkDefaultFont", 9)).grid(row=1, column=0, sticky="w", pady=(1, 6))

    list_panel = tk.Frame(card, background="#ffffff")
    list_panel.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
    list_panel.columnconfigure(0, weight=1)
    list_panel.rowconfigure(0, weight=1)
    tree = ttk.Treeview(list_panel, columns=("title",), show="", selectmode="browse", height=5)
    tree.column("title", width=165, stretch=True)
    tree.grid(row=0, column=0, sticky="nsew")
    tree.bind("<<TreeviewSelect>>", handle_when_user_selects_conversation)
    ttk.Button(list_panel, text="New Conversation", command=handle_when_user_creates_conversation).grid(row=1, column=0, sticky="w", pady=(6, 0))

    editor = tk.Frame(card, background="#ffffff")
    editor.grid(row=0, column=1, rowspan=3, sticky="nsew")
    editor.columnconfigure(1, weight=1)
    editor.columnconfigure(2, weight=0)
    date_entry = build_conversation_entry(editor, "Date", 0)
    title_entry = build_conversation_entry(editor, "Title", 1)
    url_entry = build_conversation_entry(editor, "URL", 2)
    ttk.Button(editor, text="Open", width=5, command=handle_when_user_opens_conversation_url).grid(row=2, column=2, padx=(6, 0))
    hook_entry = build_conversation_entry(editor, "Hook", 3)
    title_entry.grid_configure(columnspan=2)
    hook_entry.grid_configure(columnspan=2)
    description = tk.Label(editor, text="", background="#f2f5f8", foreground="#263746", cursor="hand2", justify="left", anchor="nw", wraplength=330, padx=6, pady=5)
    description.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(7, 0))
    description.bind("<Double-Button-1>", handle_when_user_double_clicks_conversation_description)
    ttk.Button(editor, text="Save", width=4, command=handle_when_user_saves_conversation_to_memory).grid(row=5, column=2, sticky="e", pady=(6, 0))
    for entry in [date_entry, title_entry, url_entry, hook_entry]:
        entry.bind("<KeyRelease>", handle_when_conversation_editor_changes)
    widgets["conversation-tree"] = tree
    widgets["conversation-date"] = date_entry
    widgets["conversation-title"] = title_entry
    widgets["conversation-url"] = url_entry
    widgets["conversation-hook"] = hook_entry
    widgets["conversation-description"] = description
    description_editor.set_description_save_handler(save_conversation_description_from_dialog)


def build_conversation_entry(parent: tk.Frame, label: str, row: int) -> ttk.Entry:
    """Create one compact labeled conversation entry field."""
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 6), pady=2)
    entry = ttk.Entry(parent)
    entry.grid(row=row, column=1, sticky="ew", pady=2)
    return entry


def load_conversation_register() -> None:
    """Load the preserved conversation document into the master-detail register."""
    g["conversations-document"] = load_conversations(g["project-root"])
    g["selected-conversation-id"] = None
    g["conversation-editor-dirty"] = False
    g["conversations-dirty"] = False
    rebuild_conversation_tree()
    select_topmost_conversation()


def rebuild_conversation_tree() -> None:
    """Project conversations newest-first while preserving the current selection."""
    tree = widgets["conversation-tree"]
    tree.delete(*tree.get_children())
    items = sorted(g["conversations-document"]["items"], key=get_conversation_sort_key, reverse=True)
    for item in items:
        tree.insert("", "end", iid=item["id"], values=(get_conversation_label(item),))
    selected_id = g["selected-conversation-id"]
    if selected_id and tree.exists(selected_id):
        tree.selection_set(selected_id)
        tree.focus(selected_id)


def select_topmost_conversation() -> None:
    """Select the newest visible conversation when the register first opens."""
    tree = widgets["conversation-tree"]
    conversation_ids = tree.get_children()
    if not conversation_ids:
        clear_conversation_editor()
        return
    g["selected-conversation-id"] = conversation_ids[0]
    tree.selection_set(conversation_ids[0])
    tree.focus(conversation_ids[0])
    load_selected_conversation_into_editor()


def get_conversation_sort_key(item: dict) -> str:
    """Use ISO dates for a simple newest-first lifeline order."""
    return str(item.get("date") or "")


def get_conversation_label(item: dict) -> str:
    """Give each conversation a useful single-column label."""
    if str(item.get("title") or "").strip():
        return item["title"]
    if str(item.get("date") or "").strip():
        return item["date"]
    return "Untitled conversation"


def handle_when_user_selects_conversation(event: tk.Event) -> None:
    """Commit the outgoing RAM edit before loading the newly selected conversation."""
    selected = widgets["conversation-tree"].selection()
    if not selected or selected[0] == g["selected-conversation-id"]:
        return
    save_conversation_editor_to_memory()
    g["selected-conversation-id"] = selected[0]
    load_selected_conversation_into_editor()


def load_selected_conversation_into_editor() -> None:
    """Overwrite the detail pane with the selected conversation's preserved fields."""
    item = get_selected_conversation()
    if item is None:
        clear_conversation_editor()
        return
    set_conversation_entry("conversation-date", item.get("date", ""))
    set_conversation_entry("conversation-title", item.get("title", ""))
    set_conversation_entry("conversation-url", item.get("url", ""))
    set_conversation_entry("conversation-hook", item.get("hook", ""))
    widgets["conversation-description"].configure(text=item.get("description", ""))
    g["conversation-editor-dirty"] = False


def clear_conversation_editor() -> None:
    """Clear the detail controls when no conversation is selected."""
    for key in ["conversation-date", "conversation-title", "conversation-url", "conversation-hook"]:
        set_conversation_entry(key, "")
    widgets["conversation-description"].configure(text="")
    g["conversation-editor-dirty"] = False


def set_conversation_entry(key: str, value: object) -> None:
    """Replace one single-line editor value without changing its meaning."""
    entry = widgets[key]
    entry.delete(0, tk.END)
    entry.insert(0, str(value))


def get_selected_conversation() -> dict | None:
    """Find the selected conversation in the preserved document."""
    selected_id = g["selected-conversation-id"]
    for item in g["conversations-document"]["items"]:
        if item.get("id") == selected_id:
            return item
    return None


def handle_when_conversation_editor_changes(event: tk.Event) -> None:
    """Mark a detail-pane edit as RAM-dirty without writing it to disk yet."""
    if g["selected-conversation-id"] is not None:
        g["conversation-editor-dirty"] = True
        g["conversations-dirty"] = True
        g["is-dirty"] = True
        project_window_title()


def handle_when_user_saves_conversation_to_memory() -> None:
    """Commit the editor controls into the in-memory conversation document."""
    if save_conversation_editor_to_memory():
        g["status"] = "Conversation saved in memory."
        project_status()


def save_conversation_editor_to_memory() -> bool:
    """Merge current editor fields into the selected item, preserving unfamiliar fields."""
    item = get_selected_conversation()
    if item is None or not g["conversation-editor-dirty"]:
        return False
    item["date"] = widgets["conversation-date"].get()
    item["title"] = widgets["conversation-title"].get()
    item["url"] = widgets["conversation-url"].get()
    item["hook"] = widgets["conversation-hook"].get()
    g["conversation-editor-dirty"] = False
    g["conversations-dirty"] = True
    g["is-dirty"] = True
    rebuild_conversation_tree()
    project_window_title()
    return True


def handle_when_user_creates_conversation() -> None:
    """Create one immediately selected, RAM-only conversation entry."""
    save_conversation_editor_to_memory()
    item = {
        "id": str(uuid.uuid4()),
        "date": date.today().isoformat(),
        "title": "",
        "url": "",
        "hook": "",
        "description": "",
    }
    g["conversations-document"]["items"].append(item)
    g["selected-conversation-id"] = item["id"]
    g["conversations-dirty"] = True
    g["is-dirty"] = True
    rebuild_conversation_tree()
    load_selected_conversation_into_editor()
    widgets["conversation-title"].focus_set()
    project_window_title()
    g["status"] = "New conversation created in memory."
    project_status()


def handle_when_user_opens_conversation_url() -> None:
    """Open the selected conversation's URL with the system default browser."""
    url = widgets["conversation-url"].get().strip()
    if url:
        webbrowser.open(url)
        g["status"] = "Conversation URL opened."
    else:
        g["status"] = "This conversation has no URL yet."
    project_status()


def handle_when_user_double_clicks_conversation_description(event: tk.Event) -> None:
    """Open the selected conversation's multiline description in its own small window."""
    item = get_selected_conversation()
    if item is None:
        return
    description_editor.open_description_editor({
        "parent": widgets["window"],
        "date": item.get("date") or "Undated conversation",
        "title": item.get("title") or "Untitled conversation",
        "description": item.get("description", ""),
    })


def save_conversation_description_from_dialog(text: str) -> None:
    """Accept a dialog-confirmed description into RAM while preserving other fields."""
    item = get_selected_conversation()
    if item is None:
        return
    item["description"] = text
    widgets["conversation-description"].configure(text=text)
    g["conversations-dirty"] = True
    g["is-dirty"] = True
    project_window_title()
    g["status"] = "Conversation description saved in memory."
    project_status()


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

    editor = tk.Text(card, wrap="word", undo=True, height=7, font=("TkFixedFont", 11), padx=10, pady=10, relief="solid", borderwidth=1)
    editor.grid(row=2, column=0, sticky="nsew", padx=(0, 10))
    editor.bind("<<Modified>>", handle_when_whiteboard_text_changes)
    widgets["whiteboard-editor"] = editor

    history = tk.Frame(card, background="#f2f5f8", padx=6, pady=8, width=52)
    history.grid(row=2, column=1, sticky="ns")
    history.grid_propagate(False)
    scale = tk.Scale(history, from_=0, to=0, orient="vertical", resolution=1, showvalue=False, length=145, command=handle_when_snapshot_scale_changes, background="#f2f5f8", highlightthickness=0)
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
    load_dictionary_entry_for_project()
    dictionary_identity = g["dictionary-document"]["identity"]
    name = dictionary_identity.get("name") or identity.get("name") or root.name
    title = dictionary_identity.get("title") or name
    g["project-name"] = title
    g["project-guid"] = str(identity.get("zookeep-project-guid") or "")
    hook = dictionary_identity.get("hook", "")
    project_window_title()
    widgets["title"].configure(text=f"PyDeck 26: {title}")
    widgets["hook"].configure(text=hook or "No project hook has been recorded yet.")
    widgets["project-root-path"].configure(text=str(root))
    widgets["project-guid"].configure(text=f"(zookeep ID: {g['project-guid']})" if g["project-guid"] else "")
    if is_initialized(root):
        widgets["initialization-panel"].grid_remove()
        load_current_whiteboard_from_disk()
        refresh_snapshot_navigation()
        load_conversation_register()
        g["status"] = "Current"
    else:
        show_initialization_state()
    project_status()


def load_dictionary_entry_for_project() -> None:
    """Load a preserved dictionary entry or create a RAM-only starter identity."""
    document = load_dictionary_entry(g["project-root"])
    if document is None:
        document = make_dictionary_starter_entry()
    identity = document.get("identity")
    if not isinstance(identity, dict):
        identity = {}
        document["identity"] = identity
    snapshot_identity = g["snapshot"]["identity"]
    default_name = snapshot_identity.get("name") or g["project-root"].name
    document.setdefault("id", default_name)
    identity.setdefault("name", default_name)
    identity.setdefault("title", make_dictionary_display_title(identity["name"]))
    identity.setdefault("tags", [])
    identity.setdefault("hook", "")
    g["dictionary-document"] = document
    g["dictionary-dirty"] = False
    populate_dictionary_editor()


def make_dictionary_starter_entry() -> dict:
    """Make a useful unsaved dictionary starter from existing project identity."""
    identity = g["snapshot"]["identity"]
    name = identity.get("name") or g["project-root"].name
    return {
        "id": name,
        "identity": {
            "name": name,
            "title": make_dictionary_display_title(name),
            "tags": [],
            "hook": "",
        },
    }


def make_dictionary_display_title(name: str) -> str:
    """Turn a compact project identifier into a small human-facing fallback title."""
    return re.sub(r"(?<=\D)(?=\d)", " ", name.replace("-", " ").replace("_", " ")).title()


def populate_dictionary_editor() -> None:
    """Project the four compact editable dictionary fields into the cockpit pane."""
    identity = g["dictionary-document"]["identity"]
    set_dictionary_entry("dictionary-name", identity.get("name", ""))
    set_dictionary_entry("dictionary-title", identity.get("title", ""))
    tags = identity.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    set_dictionary_entry("dictionary-tags", " ".join(str(tag) for tag in tags))
    set_dictionary_entry("dictionary-hook", identity.get("hook", ""))


def set_dictionary_entry(key: str, value: object) -> None:
    """Replace one compact dictionary single-line value."""
    entry = widgets[key]
    entry.delete(0, tk.END)
    entry.insert(0, str(value))


def handle_when_dictionary_editor_changes(event: tk.Event) -> None:
    """Mark compact dictionary changes dirty until an explicit project save."""
    g["dictionary-dirty"] = True
    g["is-dirty"] = True
    project_window_title()


def handle_when_user_saves_dictionary() -> None:
    """Write the compact dictionary fields and update the masthead immediately."""
    save_dictionary_editor_to_disk()
    g["status"] = "Dictionary entry saved."
    project_status()


def save_dictionary_editor_to_disk() -> None:
    """Update only compact identity fields while preserving the rest of the entry."""
    identity = g["dictionary-document"]["identity"]
    identity["name"] = widgets["dictionary-name"].get()
    identity["title"] = widgets["dictionary-title"].get()
    identity["tags"] = widgets["dictionary-tags"].get().split()
    identity["hook"] = widgets["dictionary-hook"].get()
    save_dictionary_entry(g["project-root"], g["dictionary-document"])
    g["dictionary-dirty"] = False
    refresh_masthead_from_dictionary()
    project_window_title()


def refresh_masthead_from_dictionary() -> None:
    """Update the persistent orientation masthead from the current dictionary identity."""
    identity = g["dictionary-document"]["identity"]
    name = identity.get("name") or g["snapshot"]["identity"].get("name") or g["project-root"].name
    title = identity.get("title") or name
    g["project-name"] = title
    widgets["title"].configure(text=f"PyDeck 26: {title}")
    widgets["hook"].configure(text=identity.get("hook") or "No project hook has been recorded yet.")


def handle_when_user_opens_full_dictionary_entry() -> None:
    """Open the deliberately modest placeholder for the later expanded dictionary editor."""
    window = tk.Toplevel(widgets["window"])
    window.title("PyDeck 26: Full Dictionary Entry")
    tk.Label(window, text="The full structured dictionary editor is not implemented yet.", padx=20, pady=20).pack()


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
    load_current_whiteboard_from_disk()
    refresh_snapshot_navigation()
    load_conversation_register()
    g["status"] = "Current"
    project_status()


def load_current_whiteboard_from_disk() -> None:
    """Load saved current text once, then display it as the active present."""
    g["current-text"] = load_whiteboard(g["project-root"])
    g["is-dirty"] = False
    g["whiteboard-dirty"] = False
    show_current_whiteboard()


def show_current_whiteboard() -> None:
    """Display in-memory current text without discarding unsaved edits."""
    set_editor_text(g["current-text"])
    widgets["whiteboard-editor"].configure(state="normal")
    g["view-index"] = 0
    project_window_title()


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
        show_current_whiteboard()
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


def handle_when_user_uses_project_save_shortcut(event: tk.Event) -> str:
    """Save all current PyDeck project state, regardless of the focused widget."""
    save_all_current_project_state()
    return "break"


def save_all_current_project_state() -> None:
    """Persist every mutable cockpit region that exists in this implementation."""
    if not is_initialized(g["project-root"]):
        g["status"] = "Initialize PyDeck 26 before saving project state."
    else:
        save_conversation_editor_to_memory()
        save_whiteboard(g["project-root"], g["current-text"])
        if g["dictionary-dirty"]:
            save_dictionary_editor_to_disk()
        if g["conversations-dirty"]:
            save_conversations(g["project-root"], g["conversations-document"])
            g["conversations-dirty"] = False
        g["is-dirty"] = False
        g["whiteboard-dirty"] = False
        project_window_title()
        g["status"] = "Project state saved."
    project_status()


def handle_when_whiteboard_text_changes(event: tk.Event) -> None:
    """Mark edits dirty and promote recalled history into a new current Whiteboard."""
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
    g["is-dirty"] = True
    g["whiteboard-dirty"] = True
    project_window_title()
    g["status"] = "Current"
    project_status()


def handle_when_user_clicks_project_root_path(event: tk.Event) -> None:
    """Open the bound project root in Windows Explorer."""
    os.startfile(g["project-root"])


def handle_when_user_clicks_project_title(event: tk.Event) -> None:
    """Copy the displayed masthead title for use in other project tools."""
    copy_text_to_clipboard(widgets["title"].cget("text"))
    g["status"] = "Project title copied to clipboard."
    project_status()


def handle_when_user_clicks_project_guid(event: tk.Event) -> None:
    """Copy the Zoo project-folder GUID without exposing a noisy control."""
    if g["project-guid"]:
        copy_text_to_clipboard(g["project-guid"])
        g["status"] = "Zoo project GUID copied to clipboard."
        project_status()


def handle_when_lionscliapp_forwards_message(message: dict) -> None:
    """Raise the cockpit when LionsCLIApp forwards a later invocation."""
    if message.get("type") == "summon":
        app.bring_window_to_front(widgets["window"])


def handle_when_user_closes_main_cockpit() -> None:
    """End the Tk runtime when its cockpit window closes."""
    save_all_current_project_state()
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


def copy_text_to_clipboard(text: str) -> None:
    """Put ordinary text on the Windows clipboard for immediate pasting."""
    window = widgets["window"]
    window.clipboard_clear()
    window.clipboard_append(text)
    window.update()


def project_status() -> None:
    """Project the current runtime status message."""
    widgets["status"].configure(text=g["status"])


def project_window_title() -> None:
    """Put a small dirty marker in the native title bar when project state changed."""
    is_dirty = g["whiteboard-dirty"] or g["conversations-dirty"] or g["dictionary-dirty"]
    dirty = "[*] " if is_dirty else ""
    widgets["window"].title(f"{dirty}PyDeck 26: {g['project-name']}")
