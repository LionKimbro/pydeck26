"""Tk machine: widgets and editor drafts; only plain events cross into Core."""

from copy import deepcopy
import os
from pathlib import Path
from queue import Empty
import tkinter as tk
from tkinter import filedialog, simpledialog, ttk

from .theme import COLORS, apply_theme
import webbrowser

import lionscliapp as app

from . import captains_log_ui, description_editor, framing, full_dictionary_editor, git_ui, ideas, image_ui, machine, panel_geometry, resource_editor, sweeper_ui

g = {"project-root": None, "commands": None, "seq": 0, "view": None,
     "projecting": False, "closing": False, "conversation-id": None,
     "resource-index": None}
widgets = {}  # Tk objects never leave the main thread.
notes_editors = {}  # Panel identity -> active tab's independent Notes Text widget.
conversation_draft = {"id": None, "fields": {}}  # Tk-owned current draft/last submission.


def initialize_tk_state(project_root):
    g.update({"project-root": Path(project_root), "commands": None, "seq": 0,
              "view": None, "projecting": False, "closing": False,
              "conversation-id": None, "resource-index": None})
    widgets.clear()
    notes_editors.clear()
    conversation_draft.update({"id": None, "fields": {}})


def send(event):
    if g["projecting"] or g["closing"]:
        return
    g["seq"] += 1
    machine.machines["CORE"]["inbox"].put({**deepcopy(event), "seq": g["seq"]})


def handle_when_polling_core_commands():
    root = widgets["window"].master
    machine.reap_exited_machines()
    if machine.fatal.is_set():
        root.destroy()
        return
    try:
        while True:
            command = g["commands"].get_nowait()
            if machine.fatal.is_set():
                root.destroy()
                return
            if command["type"] == "SHUTDOWN_COMPLETE":
                root.destroy()
                return
            if command["type"] == "STATE":
                flush_pending_text_edits()
                if command["seq"] >= g["seq"]:
                    project_core_state(command)
            elif command["type"] == "OPEN_PATH":
                try:
                    os.startfile(command["path"])
                except OSError as error:
                    send({"type": "STATUS", "text": str(error)})
            elif command["type"] == "COPY_PATH":
                copy_text_to_clipboard(command["path"])
            elif command["type"] == "COPY_TEXT":
                copy_text_to_clipboard(command["text"])
                send({"type": "STATUS", "text": "Structure JSON copied to clipboard."})
            elif command["type"] == "SET_IMAGE_PREVIEW":
                image_ui.apply_preview(command)
            elif command["type"] == "GIT_STATE":
                git_ui.project_git_state(command)
            elif command["type"] == "CAPTAINS_LOG_RESULT":
                captains_log_ui.apply_result(command)
            elif command["type"] == "SWEEPER_RESULT":
                sweeper_ui.apply_result(command)
    except Empty:
        pass
    root.after(20, handle_when_polling_core_commands)


def project_core_state(view):
    """Project independent Core records without turning projections into edits."""
    g["projecting"] = True
    try:
        g["view"] = view
        if not view["ready"]:
            return
        documents = view["documents"]
        framing.project_workspace(documents["workspace"])
        panel_geometry.project_geometry(documents["workspace"])
        image_ui.project_panels(documents["workspace"], view.get("image-states", {}))
        captains_log_ui.project_entries(view.get("captains-log-entries", []), view["initialized"])
        identity = documents["dictionary"]["identity"]
        title = identity.get("title") or identity.get("name") or g["project-root"].name
        widgets["title"].configure(text=f"PyDeck 26: {title}")
        widgets["hook"].configure(text=identity.get("hook") or "No project hook has been recorded yet.")
        widgets["project-root-path"].configure(text=view["snapshot"]["root"])
        guid = view["snapshot"]["identity"].get("zookeep-project-guid", "")
        widgets["project-guid"].configure(text=f"(zookeep ID: {guid})" if guid else "")
        coordinates = documents["dictionary"].get("coordinates")
        spark_id = coordinates.get("spark-id") if isinstance(coordinates, dict) else None
        if isinstance(spark_id, str) and spark_id.strip():
            widgets["spark-guid"].configure(text=f"(spark ID: {spark_id})")
            widgets["spark-guid"].pack(side="left", padx=(8, 0))
        else:
            widgets["spark-guid"].configure(text="")
            widgets["spark-guid"].pack_forget()
        marker = "[*] " if view["dirty"] else ""
        widgets["window"].title(f"{marker}PyDeck 26: {title}")
        for key in ("name", "title", "tags", "hook"):
            if f"dictionary-{key}" not in widgets:
                continue
            value = identity.get(key, "")
            if key == "tags":
                value = " ".join(map(str, value)) if isinstance(value, list) else ""
            set_entry_text(widgets[f"dictionary-{key}"], value)
        if view["initialized"]:
            widgets["project-initialization"].pack_forget()
        else:
            widgets["project-initialization"].pack(fill="x", before=widgets["workspace-root"])
        if "whiteboard-editor" in widgets:
            editor = widgets["whiteboard-editor"]
            text = view["view-text"] if view["initialized"] else "Initialize PyDeck 26 to open this project's Whiteboard."
            if editor.get("1.0", "end-1c") != text:
                editor.configure(state="normal")
                editor.delete("1.0", "end")
                editor.insert("1.0", text)
            editor.edit_modified(False)
            editor.configure(state="normal" if view["initialized"] and not g["closing"] else "disabled")
            widgets["snapshot-scale"].configure(to=view["history-count"], state="normal" if view["initialized"] else "disabled")
            widgets["snapshot-scale"].set(view["view-index"])
        project_resource_rows(documents["resources"])
        project_conversation_rows(documents["conversations"], view["selected-conversation-id"])
        if "ideas-tree" in widgets:
            tree = widgets["ideas-tree"]
            tree.delete(*tree.get_children())
            for item in documents["ideas"]["items"]:
                if item.get("pinned"):
                    tree.insert("", "end", iid=item["guid"], values=(item.get("status", ""), item.get("title", ""), item.get("hook", "")))
        for panel_id, editor in notes_editors.items():
            text = documents["workspace"]["panels"][panel_id]["text"]
            if editor.get("1.0", "end-1c") != text:
                editor.delete("1.0", "end")
                editor.insert("1.0", text)
            editor.edit_modified(False)
        ideas.set_context({"root": widgets["window"], "document": deepcopy(documents["ideas"]),
                           "save": save_idea_from_editor})
        ideas.refresh_directory()
        full_dictionary_editor.update_source_document(documents["dictionary"])
        widgets["status"].configure(text=view["status"])
    finally:
        g["projecting"] = False


def set_entry_text(entry, value):
    value = str(value)
    if entry.get() != value:
        entry.delete(0, tk.END)
        entry.insert(0, value)


def project_resource_rows(document):
    if "resources-tree" not in widgets:
        return
    tree = widgets["resources-tree"]
    selected = tree.selection()
    tree.delete(*tree.get_children())
    for index, item in enumerate(document["items"]):
        tree.insert("", "end", iid=str(index), values=tuple(item.get(key, "") for key in ("path", "filename", "hook")))
    selection = str(g["resource-index"]) if g["resource-index"] is not None else (selected[0] if selected else None)
    if selection is not None and tree.exists(selection):
        tree.selection_set(selection)
        tree.focus(selection)
    g["resource-index"] = None


def project_conversation_rows(document, selected_id):
    if "conversation-tree" not in widgets:
        g["conversation-id"] = None
        return
    tree = widgets["conversation-tree"]
    ordered = sorted(document["items"], key=lambda item: str(item.get("date") or ""), reverse=True)
    wanted = {item["id"] for item in ordered}
    for item_id in tree.get_children():
        if item_id not in wanted:
            tree.delete(item_id)
    for index, item in enumerate(ordered):
        item_id = item["id"]
        values = tuple(str(item.get(key) or "") for key in ("date", "title", "hook"))
        if tree.exists(item_id):
            if tree.item(item_id, "values") != values:
                tree.item(item_id, values=values)
            if tree.index(item_id) != index:
                tree.move(item_id, "", index)
        else:
            tree.insert("", index, iid=item_id, values=values)
    g["conversation-id"] = selected_id
    item = next((item for item in document["items"] if item["id"] == selected_id), {})
    if selected_id and tree.exists(selected_id) and tree.selection() != (selected_id,):
        tree.selection_set(selected_id)
        tree.focus(selected_id)
    # Loading another record (or rebuilding its widgets) is an explicit editor load.
    # Routine projections/save acknowledgements must not echo text into the live draft.
    if selected_id != conversation_draft["id"]:
        fields = {key: str(item.get(key) or "") for key in ("date", "title", "url", "hook")}
        for key, value in fields.items():
            set_entry_text(widgets[f"conversation-{key}"], value)
        conversation_draft.update({"id": selected_id, "fields": fields})
    widgets["conversation-description"].configure(text=item.get("description", ""))


def handle_when_dictionary_editor_changes(event=None):
    if not g["view"] or g["projecting"] or "dictionary-name" not in widgets:
        return
    identity = {key: widgets[f"dictionary-{key}"].get() for key in ("name", "title", "hook")}
    identity["tags"] = widgets["dictionary-tags"].get().split()
    if identity != {key: g["view"]["documents"]["dictionary"]["identity"].get(key) for key in identity}:
        send({"type": "DICTIONARY_EDIT", "identity": identity})


def handle_when_user_opens_full_dictionary_entry():
    if not g["view"]:
        return
    full_dictionary_editor.set_full_dictionary_callbacks({"save": save_full_dictionary_additional_fields,
                                                        "status": set_full_dictionary_status})
    document = g["view"]["documents"]["dictionary"]
    full_dictionary_editor.open_full_dictionary_editor({"parent": widgets["window"],
        "name": document["identity"].get("name", ""), "document": deepcopy(document)})


def save_full_dictionary_additional_fields(additional):
    send({"type": "DICTIONARY_ADDITIONAL", "additional": additional})


def set_full_dictionary_status(text):
    # Validation is local; persistence confirmation comes from Core.
    widgets["status"].configure(text=text)


def handle_when_conversation_editor_changes(event=None):
    if g["conversation-id"] is None or g["projecting"]:
        return
    fields = {key: widgets[f"conversation-{key}"].get() for key in ("date", "title", "url", "hook")}
    if fields != conversation_draft["fields"]:
        conversation_draft.update({"id": g["conversation-id"], "fields": dict(fields)})
        send({"type": "CONVERSATION_EDIT", "id": g["conversation-id"], "fields": fields})


def handle_when_user_selects_conversation(event=None):
    selected = widgets["conversation-tree"].selection()
    if g["projecting"] or not selected or selected[0] == g["conversation-id"]:
        return
    handle_when_conversation_editor_changes()
    send({"type": "SELECT_CONVERSATION", "id": selected[0]})


def handle_when_user_creates_conversation():
    handle_when_conversation_editor_changes()
    send({"type": "NEW_CONVERSATION"})


def handle_when_user_saves_conversation_to_memory():
    handle_when_conversation_editor_changes()
    send({"type": "STATUS", "text": "Conversation saved in memory."})


def handle_when_user_opens_conversation_url():
    url = widgets["conversation-url"].get().strip()
    if url:
        webbrowser.open(url)


def handle_when_user_double_clicks_conversation_description(event):
    item_id = g["conversation-id"]
    if item_id is None:
        return
    # Capture identity, not a mutable 'current selection', for the dialog's lifetime.
    description_editor.set_description_save_handler(
        lambda text: send({"type": "CONVERSATION_EDIT", "id": item_id, "fields": {"description": text}}))
    description_editor.open_description_editor({"parent": widgets["window"],
        "date": widgets["conversation-date"].get() or "Undated conversation",
        "title": widgets["conversation-title"].get() or "Untitled conversation",
        "description": widgets["conversation-description"].cget("text")})


def save_idea_from_editor(item):
    send({"type": "IDEA_SAVE", "item": item})


def is_project_initialized():
    return bool(g["view"] and g["view"]["initialized"])


def handle_when_user_adds_resource():
    if not is_project_initialized():
        return
    path = filedialog.askopenfilename(parent=widgets["window"], initialdir=g["project-root"], title="Add Existing Project Resource")
    if path:
        send({"type": "RESOURCE_ADD", "path": path, "kind": "file"})


def handle_when_user_copies_structure_json():
    if g["view"] and g["view"]["ready"]:
        send({"type": "COPY_STRUCTURE"})


def handle_when_user_adds_resource_folder():
    if not is_project_initialized():
        return
    path = filedialog.askdirectory(parent=widgets["window"], initialdir=g["project-root"], title="Add Existing Project Folder")
    if path:
        send({"type": "RESOURCE_ADD", "path": path, "kind": "folder"})


def get_selected_resource_index():
    if "resources-tree" not in widgets:
        return None
    selected = widgets["resources-tree"].selection()
    return int(selected[0]) if selected else None


def handle_when_user_removes_resource():
    index = get_selected_resource_index()
    if index is not None:
        send({"type": "RESOURCE_REMOVE", "index": index})


def handle_when_user_double_clicks_resource(event):
    tree = widgets["resources-tree"]
    row = tree.identify_row(event.y)
    column = tree.identify_column(event.x)
    if not row or not g["view"]:
        return
    index = int(row)
    tree.selection_set(row)
    item = g["view"]["documents"]["resources"]["items"][index]
    if column in {"#1", "#2"}:
        send({"type": "RESOURCE_ACTION", "item": item,
              "action": "COPY_PATH" if column == "#1" else "OPEN_PATH"})
    elif column == "#3":
        resource_editor.set_resource_save_handler(
            lambda record: send({"type": "RESOURCE_EDIT", "index": index, "item": record}))
        resource_editor.open_resource_editor({"parent": widgets["window"], "title": "Edit Resource Hook",
                                              "item": deepcopy(item), "hook-only": True})


def move_selected_resource(change):
    index = get_selected_resource_index()
    if index is not None:
        g["resource-index"] = index + change
        send({"type": "RESOURCE_MOVE", "index": index, "change": change})


def move_selected_resource_up():
    move_selected_resource(-1)


def move_selected_resource_down():
    move_selected_resource(1)


def handle_when_user_moves_resource_up(event):
    move_selected_resource_up()
    return "break"


def handle_when_user_moves_resource_down(event):
    move_selected_resource_down()
    return "break"


def handle_when_whiteboard_text_changes(event=None):
    if "whiteboard-editor" not in widgets:
        return
    editor = widgets["whiteboard-editor"]
    if not editor.edit_modified():
        return
    editor.edit_modified(False)
    if g["projecting"] or not is_project_initialized():
        return
    send({"type": "WHITEBOARD_EDIT", "text": editor.get("1.0", "end-1c")})


def handle_when_snapshot_scale_changes(value):
    if g["projecting"] or not g["view"]:
        return
    index = int(float(value))
    if index != g["view"]["view-index"]:
        handle_when_whiteboard_text_changes()
        send({"type": "HISTORY_SELECT", "index": index})


def handle_when_user_saves_snapshot():
    handle_when_whiteboard_text_changes()
    send({"type": "SNAPSHOT"})


def handle_when_user_initializes_project():
    send({"type": "INITIALIZE"})


def flush_editor_drafts():
    captains_log_ui.capture_draft()
    image_ui.flush_strokes()
    handle_when_dictionary_editor_changes()
    handle_when_conversation_editor_changes()
    handle_when_whiteboard_text_changes()
    for panel_id in list(notes_editors):
        handle_when_notes_text_changes(panel_id)
    return full_dictionary_editor.flush_pending_edit()


def flush_pending_text_edits():
    """Publish queued Text modifications before an asynchronous projection can replace them."""
    captains_log_ui.capture_draft()
    handle_when_whiteboard_text_changes()
    for panel_id in list(notes_editors):
        handle_when_notes_text_changes(panel_id)


def clear_panel_widgets():
    panel_geometry.clear_panels()
    captains_log_ui.clear_panels()
    git_ui.clear_panels()
    image_ui.clear_panels()
    for key in list(widgets):
        if key.startswith(("dictionary-", "conversation-", "resources-", "ideas-", "whiteboard-", "snapshot-")) or key in {"cockpit-surface", "initialization-panel"}:
            del widgets[key]
    notes_editors.clear()
    g["conversation-id"] = None
    conversation_draft.update({"id": None, "fields": {}})


def build_hosted_panel(details):
    panel = details["panel"]
    if panel["type"] == "CAPTAINS_LOG":
        return captains_log_ui.build_panel(details)
    if panel["type"] == "GIT":
        return git_ui.build_panel(details)
    if panel["type"] == "IMAGE":
        return image_ui.build_panel(details)
    widgets["cockpit-surface"] = details["parent"]
    builders = {"STRUCTURE": build_structure_card, "DICTIONARY": build_dictionary_card,
                "CONVERSATIONS": build_conversations_card, "IDEAS": build_ideas_card,
                "WHITEBOARD": build_whiteboard_card}
    if panel["type"] in builders:
        header = builders[panel["type"]]()
        if panel["type"] == "CONVERSATIONS":
            panel_geometry.register_split({"panel": panel, "pane": widgets["conversation-pane"]})
        return header
    else:
        parent = details["parent"]
        header = ttk.Frame(parent)
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=4)
        ttk.Label(header, text=panel["label"]).pack(side="left")
        ttk.Button(header, text="Rename", command=lambda: handle_when_user_renames_notes_panel(panel["id"])).pack(side="right")
        editor = tk.Text(parent, wrap="word", undo=True, font=("TkFixedFont", 11), padx=10, pady=10)
        editor.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=1)
        notes_editors[panel["id"]] = editor
        editor.insert("1.0", panel["text"])
        editor.edit_modified(False)
        editor.bind("<<Modified>>", lambda event: handle_when_notes_text_changes(panel["id"]))
        return header


def build_panel_title_row(parent, title):
    """One title row shared by panel-specific actions and the hosting close control."""
    header = tk.Frame(parent, background=COLORS["panel"])
    header.grid(row=0, column=0, sticky="ew")
    tk.Label(header, text=title, background=COLORS["panel"], foreground=COLORS["accent"],
             font=("TkDefaultFont", 12, "bold")).pack(side="left")
    return header


def handle_when_notes_text_changes(panel_id):
    editor = notes_editors.get(panel_id)
    if editor is not None and editor.edit_modified():
        editor.edit_modified(False)
        if not g["projecting"]:
            send({"type": "NOTES_EDIT", "panel-id": panel_id, "text": editor.get("1.0", "end-1c")})


def handle_when_user_renames_notes_panel(panel_id):
    panel = g["view"]["documents"]["workspace"]["panels"][panel_id]
    label = simpledialog.askstring("Rename Notes", "Panel name:", initialvalue=panel["label"], parent=widgets["window"])
    if label:
        framing.request({"type": "RENAME_PANEL", "panel-id": panel_id, "label": label})


def handle_when_user_uses_project_save_shortcut(event):
    if flush_editor_drafts():
        send({"type": "SAVE"})
    return "break"


def handle_when_user_closes_main_cockpit():
    if g["closing"] or not flush_editor_drafts():
        return
    send({"type": "SHUTDOWN"})
    g["closing"] = True
    # Native dialogs and draft edits cannot race with the final persistence barrier.
    widgets["window"].withdraw()


def handle_when_user_clicks_project_root_path(event):
    os.startfile(g["project-root"])


def handle_when_user_clicks_project_title(event):
    copy_text_to_clipboard(widgets["title"].cget("text"))


def handle_when_user_clicks_project_guid(event):
    if g["view"]:
        copy_text_to_clipboard(str(g["view"]["snapshot"]["identity"].get("zookeep-project-guid", "")))


def handle_when_user_clicks_spark_guid(event):
    if g["view"]:
        copy_text_to_clipboard(g["view"]["documents"]["dictionary"]["coordinates"]["spark-id"])


def handle_when_lionscliapp_forwards_message(message):
    if message.get("type") == "summon" and not g["closing"]:
        app.bring_window_to_front(widgets["window"])


def copy_text_to_clipboard(text):
    window = widgets["window"]
    window.clipboard_clear()
    window.clipboard_append(text)


def realize_main_cockpit_window(root: tk.Tk) -> None:
    """Build the one visible, resizable cockpit window."""
    apply_theme(root)
    window = tk.Toplevel(root)
    window.geometry("1120x760")
    window.minsize(820, 560)
    window.columnconfigure(0, weight=1)
    window.rowconfigure(1, weight=1)
    widgets["window"] = window
    panel_geometry.initialize_context({"window": window, "send": send})
    image_ui.initialize_context({"send": send, "window": window, "is-closing": lambda: g["closing"]})
    git_ui.initialize_context({"send": send, "window": window, "is-closing": lambda: g["closing"]})
    captains_log_ui.initialize_context({"send": send, "window": window, "is-closing": lambda: g["closing"]})
    window.bind_all("<Control-s>", handle_when_user_uses_project_save_shortcut)
    build_masthead(window)
    build_cockpit_surface(window)
    build_status_bar(window)
    window.protocol("WM_DELETE_WINDOW", handle_when_user_closes_main_cockpit)


def build_masthead(window: tk.Toplevel) -> None:
    """Create the project-orientation masthead that remains visible on resize."""
    header = tk.Frame(window, background=COLORS["top"], padx=18, pady=14)
    header.grid(row=0, column=0, sticky="ew")
    title = tk.Label(header, background=COLORS["top"], foreground=COLORS["accent"], font=("TkDefaultFont", 19, "bold"))
    title.pack(anchor="w")
    title.configure(cursor="hand2")
    title.bind("<Button-1>", handle_when_user_clicks_project_title)
    hook = tk.Label(header, background=COLORS["top"], foreground=COLORS["secondary"], font=("TkDefaultFont", 10), wraplength=1040, justify="left")
    hook.pack(anchor="w", pady=(3, 3))
    path_line = tk.Frame(header, background=COLORS["top"])
    path_line.pack(anchor="w")
    path = tk.Label(path_line, background=COLORS["top"], foreground=COLORS["accent"], cursor="hand2", font=("TkDefaultFont", 9, "underline"))
    path.pack(side="left")
    path.bind("<Button-1>", handle_when_user_clicks_project_root_path)
    guid = tk.Label(path_line, background=COLORS["top"], foreground=COLORS["muted"], cursor="hand2", font=("TkDefaultFont", 9))
    guid.pack(side="left", padx=(8, 0))
    guid.bind("<Button-1>", handle_when_user_clicks_project_guid)
    spark = tk.Label(path_line, background=COLORS["top"], foreground=COLORS["muted"], cursor="hand2", font=("TkDefaultFont", 9))
    spark.bind("<Button-1>", handle_when_user_clicks_spark_guid)
    widgets["title"] = title
    widgets["hook"] = hook
    widgets["project-root-path"] = path
    widgets["project-guid"] = guid
    widgets["spark-guid"] = spark


def build_cockpit_surface(window: tk.Toplevel) -> None:
    surface = ttk.Frame(window)
    surface.grid(row=1, column=0, sticky="nsew")
    banner = ttk.Frame(surface, padding=8)
    ttk.Label(banner, text="PyDeck 26 has not been initialized for this project.").pack(side="left")
    ttk.Button(banner, text="Initialize PyDeck 26", command=handle_when_user_initializes_project).pack(side="left", padx=12)
    body = ttk.Frame(surface)
    body.pack(fill="both", expand=True)
    widgets["project-initialization"] = banner
    widgets["workspace-root"] = body
    framing.initialize_framing({"parent": body, "window": window, "send": send,
        "sweeper-request": handle_when_user_creates_sweeper_request,
        "flush": flush_editor_drafts, "build-panel": build_hosted_panel, "clear-panels": clear_panel_widgets})





def handle_when_user_creates_sweeper_request():
    if g["closing"] or not g["view"] or not g["view"]["ready"]:
        return
    sweeper_ui.show_form({"window": widgets["window"], "send": send,
        "project-root": str(g["project-root"]),
        "tab-id": framing.g["selected-tab"]})


def build_structure_card() -> tk.Frame:
    """Build the curated, explicitly ordered project-resource instrument."""
    surface = widgets["cockpit-surface"]
    card = tk.Frame(surface, background=COLORS["panel"], highlightbackground=COLORS["border"], highlightthickness=1, padx=10, pady=10)
    card.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
    card.columnconfigure(0, weight=1)
    card.rowconfigure(2, weight=1)
    header = build_panel_title_row(card, "STRUCTURE")
    ttk.Button(header, text="Copy", command=handle_when_user_copies_structure_json).pack(side="right")
    tk.Label(card, text="curated project resources — path copies, filename opens, hook explains", background=COLORS["panel"], foreground=COLORS["secondary"], font=("TkDefaultFont", 9)).grid(row=1, column=0, sticky="w")
    tree = ttk.Treeview(card, columns=("path", "filename", "hook"), show="headings", height=5)
    for key, label, width in [("path", "Path", 120), ("filename", "Filename", 145), ("hook", "Hook", 220)]:
        tree.heading(key, text=label)
        tree.column(key, width=width, stretch=key == "hook")
    tree.grid(row=2, column=0, sticky="nsew", pady=(5, 0))
    tree.bind("<Double-Button-1>", handle_when_user_double_clicks_resource)
    tree.bind("<Control-Up>", handle_when_user_moves_resource_up)
    tree.bind("<Control-Down>", handle_when_user_moves_resource_down)
    controls = ttk.Frame(card)
    controls.grid(row=3, column=0, sticky="ew", pady=(6, 0))
    ttk.Button(controls, text="Add", command=handle_when_user_adds_resource).pack(side="left")
    ttk.Button(controls, text="Add Folder", command=handle_when_user_adds_resource_folder).pack(side="left", padx=(5, 0))
    ttk.Button(controls, text="Remove", command=handle_when_user_removes_resource).pack(side="left", padx=(5, 0))
    ttk.Button(controls, text="↑", width=3, command=move_selected_resource_up).pack(side="right")
    ttk.Button(controls, text="↓", width=3, command=move_selected_resource_down).pack(side="right", padx=(0, 5))
    widgets["resources-tree"] = tree
    return header


def build_dictionary_card() -> tk.Frame:
    """Build the compact editable identity surface for the current project dictionary."""
    surface = widgets["cockpit-surface"]
    card = tk.Frame(surface, background=COLORS["panel"], highlightbackground=COLORS["border"], highlightthickness=1, padx=10, pady=10)
    card.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
    card.columnconfigure(1, weight=1)
    header = build_panel_title_row(card, "DICTIONARY")
    header.grid_configure(columnspan=2)
    name = build_dictionary_entry(card, "Name", 1)
    title = build_dictionary_entry(card, "Title", 2)
    tags = build_dictionary_entry(card, "Tags", 3)
    hook = build_dictionary_entry(card, "Hook", 4)
    ttk.Button(card, text="Open Full Entry", command=handle_when_user_opens_full_dictionary_entry).grid(row=5, column=1, sticky="e", pady=(6, 0))
    for entry in [name, title, tags, hook]:
        entry.bind("<KeyRelease>", handle_when_dictionary_editor_changes)
    widgets["dictionary-name"] = name
    widgets["dictionary-title"] = title
    widgets["dictionary-tags"] = tags
    widgets["dictionary-hook"] = hook
    return header


def build_dictionary_entry(parent: tk.Frame, label: str, row: int) -> ttk.Entry:
    """Create one dense key-and-value dictionary row."""
    ttk.Label(parent, text=label, width=7).grid(row=row, column=0, sticky="w", padx=(0, 6), pady=2)
    entry = ttk.Entry(parent)
    entry.grid(row=row, column=1, sticky="ew", pady=2)
    return entry


def build_ideas_card() -> tk.Frame:
    """Build the compact pinned-ideas view and its directory jump."""
    surface=widgets["cockpit-surface"]; card=tk.Frame(surface,background=COLORS["panel"],highlightbackground=COLORS["border"],highlightthickness=1,padx=10,pady=10)
    card.grid(row=0,column=0,sticky="nsew",padx=5,pady=5); card.columnconfigure(0,weight=1); card.rowconfigure(2,weight=1)
    header = build_panel_title_row(card, "IDEAS")
    tk.Label(card,text="pinned possible work",background=COLORS["panel"],foreground=COLORS["secondary"],font=("TkDefaultFont",9)).grid(row=1,column=0,sticky="w")
    tree=ttk.Treeview(card,columns=("status","title","hook"),show="headings",height=5)
    for key, label, width in [("status", "Status", 95), ("title", "Title", 180), ("hook", "Hook", 210)]:
        tree.heading(key, text=label)
        tree.column(key, width=width, stretch=key != "status")
    tree.grid(row=2,column=0,sticky="nsew",pady=(5,0)); tree.bind("<Double-Button-1>",lambda e: ideas.open_editor(tree.selection()[0] if tree.selection() else None))
    ttk.Button(card,text="Directory",command=ideas.open_directory).grid(row=3,column=0,sticky="w",pady=(6,0)); widgets["ideas-tree"]=tree
    return header


def build_conversations_card() -> tk.Frame:
    """Build a compact master-detail project conversation register."""
    surface = widgets["cockpit-surface"]
    card = tk.Frame(surface, background=COLORS["panel"], highlightbackground=COLORS["border"], highlightthickness=1, padx=10, pady=10)
    card.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
    card.columnconfigure(0, weight=1)
    card.rowconfigure(2, weight=1)
    header = build_panel_title_row(card, "CONVERSATIONS")
    tk.Label(card, text="conversations with LLMs", background=COLORS["panel"], foreground=COLORS["secondary"], font=("TkDefaultFont", 9)).grid(row=1, column=0, sticky="w", pady=(1, 6))

    pane = ttk.Panedwindow(card, orient="horizontal")
    pane.grid(row=2, column=0, sticky="nsew")
    list_panel = tk.Frame(pane, background=COLORS["panel"], padx=4)
    pane.add(list_panel, weight=2)
    list_panel.columnconfigure(0, weight=1)
    list_panel.rowconfigure(0, weight=1)
    tree = ttk.Treeview(list_panel, columns=("date", "title", "hook"), show="headings", selectmode="browse", height=5)
    for key, label, width, stretch in [
        ("date", "Date", 88, False),
        ("title", "Title", 170, True),
        ("hook", "Hook", 210, True),
    ]:
        tree.heading(key, text=label)
        tree.column(key, width=width, stretch=stretch)
    tree.grid(row=0, column=0, sticky="nsew")
    scrollbar = ttk.Scrollbar(list_panel, orient="vertical", command=tree.yview)
    scrollbar.grid(row=0, column=1, sticky="ns")
    tree.configure(yscrollcommand=scrollbar.set)
    tree.bind("<<TreeviewSelect>>", handle_when_user_selects_conversation)
    ttk.Button(list_panel, text="New Conversation", command=handle_when_user_creates_conversation).grid(row=1, column=0, sticky="w", pady=(6, 0))

    editor = tk.Frame(pane, background=COLORS["panel"], padx=6)
    pane.add(editor, weight=3)
    editor.columnconfigure(1, weight=1)
    editor.columnconfigure(2, weight=0)
    date_entry = build_conversation_entry(editor, "Date", 0)
    title_entry = build_conversation_entry(editor, "Title", 1)
    url_entry = build_conversation_entry(editor, "URL", 2)
    ttk.Button(editor, text="Open", width=5, command=handle_when_user_opens_conversation_url).grid(row=2, column=2, padx=(6, 0))
    hook_entry = build_conversation_entry(editor, "Hook", 3)
    title_entry.grid_configure(columnspan=2)
    hook_entry.grid_configure(columnspan=2)
    description = tk.Label(editor, text="", background=COLORS["editor"], foreground=COLORS["text"], cursor="hand2", justify="left", anchor="nw", wraplength=330, padx=6, pady=5)
    description.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(7, 0))
    description.bind("<Double-Button-1>", handle_when_user_double_clicks_conversation_description)
    ttk.Button(editor, text="Save", width=4, command=handle_when_user_saves_conversation_to_memory).grid(row=5, column=2, sticky="e", pady=(6, 0))
    widgets["conversation-tree"] = tree
    widgets["conversation-date"] = date_entry
    widgets["conversation-title"] = title_entry
    widgets["conversation-url"] = url_entry
    widgets["conversation-hook"] = hook_entry
    widgets["conversation-description"] = description
    widgets["conversation-pane"] = pane
    return header


def build_conversation_entry(parent: tk.Frame, label: str, row: int) -> ttk.Entry:
    """Create one compact labeled conversation entry field."""
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 6), pady=2)
    variable = tk.StringVar(parent)
    entry = ttk.Entry(parent, textvariable=variable)
    widgets[f"conversation-{label.lower()}-variable"] = variable
    variable.trace_add("write", lambda *args: handle_when_conversation_editor_changes())
    entry.grid(row=row, column=1, sticky="ew", pady=2)
    return entry


def build_whiteboard_card() -> tk.Frame:
    """Build the directly editable present and its right-hand historical control."""
    surface = widgets["cockpit-surface"]
    card = tk.Frame(surface, background=COLORS["panel"], highlightbackground=COLORS["border"], highlightthickness=1, padx=14, pady=12)
    card.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
    card.columnconfigure(0, weight=1)
    card.rowconfigure(2, weight=1)
    header = build_panel_title_row(card, "WHITEBOARD")
    header.grid_configure(columnspan=2)
    tk.Label(card, text="loose intentional notes, current thinking, and recoverable earlier states", background=COLORS["panel"], foreground=COLORS["secondary"], font=("TkDefaultFont", 9)).grid(row=1, column=0, sticky="w", pady=(1, 8))

    ttk.Button(header, text="Snapshot", command=handle_when_user_saves_snapshot).pack(side="right")

    editor = tk.Text(card, wrap="word", undo=True, height=7, font=("TkFixedFont", 11), padx=10, pady=10, relief="solid", borderwidth=1)
    editor.grid(row=2, column=0, sticky="nsew", padx=(0, 10))
    editor.bind("<<Modified>>", handle_when_whiteboard_text_changes)
    widgets["whiteboard-editor"] = editor

    history = tk.Frame(card, background=COLORS["editor"], padx=6, pady=8, width=52)
    history.grid(row=2, column=1, sticky="ns")
    history.grid_propagate(False)
    scale = tk.Scale(history, from_=0, to=0, orient="vertical", resolution=1, showvalue=False, length=145, command=handle_when_snapshot_scale_changes, background=COLORS["editor"], highlightthickness=0)
    scale.pack(anchor="center", fill="y", expand=True)
    widgets["snapshot-scale"] = scale
    return header


def build_status_bar(window: tk.Toplevel) -> None:
    """Create the persistent status message area."""
    status = ttk.Label(window, anchor="w", relief="sunken", padding=(8, 4))
    status.grid(row=2, column=0, sticky="ew")
    widgets["status"] = status
    status.configure(text="Opening PyDeck 26.")
