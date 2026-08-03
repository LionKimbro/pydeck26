"""Permissive full JSON editor for dictionary fields beyond PyDeck's compact identity."""
from __future__ import annotations
import json
import tkinter as tk
from tkinter import ttk

g = {"save-fn": None, "status-fn": None, "after-id": None}
widgets = {}
reference = {
    "entry-weight": ("string", "Recommended depth for this entry.", "orientation"),
    "origin": ("string", "Where the project or concept came from.", ""),
    "coordinates": ("object", "Repositories, paths, URLs, and document IDs.", {"github": ""}),
    "outline": ("array of strings", "Main facts someone should know.", [""]),
    "design-intent": ("string or array of strings", "What the project is for and why.", [""]),
    "clarifications": ("array of strings", "Boundaries and distinctions.", [""]),
    "examples": ("array", "Representative examples.", [""]),
    "core-concepts": ("object", "Internal vocabulary and named sub-concepts.", {"concept-name": ""}),
    "constraints": ("array of strings", "Rules and limits governing correct use.", [""]),
    "related-entries": ("array of strings", "IDs of connected dictionary entries.", [""]),
}

def set_full_dictionary_callbacks(callbacks: dict) -> None:
    """Install parent save and status boundaries."""
    g["save-fn"] = callbacks["save"]
    g["status-fn"] = callbacks["status"]

def open_full_dictionary_editor(details: dict) -> None:
    """Open the resizable additional-fields editor for one canonical entry."""
    window = tk.Toplevel(details["parent"])
    window.title(f"Full Dictionary Entry — {details['name']}")
    window.geometry("920x610")
    window.minsize(650, 420)
    window.columnconfigure(0, weight=1); window.rowconfigure(0, weight=1)
    pane = ttk.Panedwindow(window, orient="horizontal")
    pane.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
    left = ttk.Frame(pane); right = ttk.Frame(pane)
    pane.add(left, weight=3); pane.add(right, weight=1)
    left.columnconfigure(0, weight=1); left.rowconfigure(0, weight=1)
    editor = tk.Text(left, wrap="none", undo=True, font=("TkFixedFont", 10))
    editor.grid(row=0, column=0, sticky="nsew")
    ybar = ttk.Scrollbar(left, orient="vertical", command=editor.yview); ybar.grid(row=0, column=1, sticky="ns")
    xbar = ttk.Scrollbar(left, orient="horizontal", command=editor.xview); xbar.grid(row=1, column=0, sticky="ew")
    editor.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
    editor.insert("1.0", json.dumps(get_additional_fields(details["document"]), indent=2, ensure_ascii=False))
    editor.bind("<<Modified>>", handle_when_json_changes)
    editor.bind("<Control-s>", handle_when_user_uses_full_entry_save_shortcut)
    tree = ttk.Treeview(right, show="tree", height=10); tree.pack(fill="both", expand=True)
    for key in reference: tree.insert("", "end", iid=key, text=key)
    tree.bind("<<TreeviewSelect>>", handle_when_reference_key_selected)
    tree.bind("<Double-Button-1>", handle_when_reference_key_inserted)
    detail = tk.Label(right, justify="left", anchor="nw", wraplength=220); detail.pack(fill="x", pady=(8,0))
    status = ttk.Label(window, anchor="w", relief="sunken", padding=(6,3)); status.grid(row=1,column=0,sticky="ew")
    buttons = ttk.Frame(window); buttons.grid(row=2,column=0,sticky="e",padx=8,pady=(0,8))
    ttk.Button(buttons,text="Format",command=handle_when_user_formats_json).pack(side="left",padx=3)
    ttk.Button(buttons,text="Copy JSON",command=handle_when_user_copies_json).pack(side="left",padx=3)
    ttk.Button(buttons,text="Copy Complete Entry",command=handle_when_user_copies_complete_entry).pack(side="left",padx=3)
    widgets.update({"window":window,"editor":editor,"tree":tree,"detail":detail,"status":status,"document":details["document"]})
    editor.edit_modified(False); set_status("JSON valid. Autosaved.")

def get_additional_fields(document: dict) -> dict:
    """Extract only editable non-basic top-level fields."""
    return {key:value for key,value in document.items() if key not in {"id","identity"}}

def handle_when_json_changes(event: tk.Event) -> None:
    """Debounce validation and valid-only autosave after edits."""
    if not widgets["editor"].edit_modified(): return
    widgets["editor"].edit_modified(False)
    if g["after-id"]: widgets["window"].after_cancel(g["after-id"])
    g["after-id"] = widgets["window"].after(650, validate_and_autosave)

def validate_and_autosave() -> dict | None:
    """Validate JSON, visually locate failures, and save only a valid additional object."""
    result = parse_additional_json()
    if result is None: return None
    clear_error_tags(); g["save-fn"](result); set_status("JSON valid. Autosaved."); return result

def parse_additional_json() -> dict | None:
    """Parse the editor's additional object with precise reserved-key feedback."""
    text = widgets["editor"].get("1.0","end-1c")
    try: data = json.loads(text)
    except json.JSONDecodeError as exc:
        show_json_error(exc); return None
    if not isinstance(data,dict): set_status("Additional dictionary JSON must be an object."); return None
    for key in ["id","identity"]:
        if key in data: set_status(f'Reserved key "{key}" is edited in the compact Dictionary pane.'); return None
    return data

def show_json_error(exc: json.JSONDecodeError) -> None:
    """Mark the exact parser location without obscuring the remainder of the document."""
    editor=widgets["editor"]; clear_error_tags(); index=f"1.0+{exc.pos}c"; line=f"{exc.lineno}.0"
    editor.tag_add("json-error-line",line,f"{exc.lineno}.end"); editor.tag_add("json-error-char",index,f"{index}+1c")
    editor.tag_configure("json-error-line",background="#fff0f0"); editor.tag_configure("json-error-char",background="#f2a5a5")
    editor.mark_set("insert",index); editor.see(index); set_status(f"JSON error at line {exc.lineno}, column {exc.colno}: {exc.msg}")

def clear_error_tags() -> None:
    """Clear only JSON validation styling."""
    editor=widgets["editor"]; editor.tag_remove("json-error-line","1.0","end"); editor.tag_remove("json-error-char","1.0","end")

def handle_when_reference_key_selected(event: tk.Event) -> None:
    """Show a concise description and skeleton example for a reference key."""
    selected=widgets["tree"].selection()
    if not selected:return
    key=selected[0]; kind,purpose,value=reference[key]
    widgets["detail"].configure(text=f"{key}\n\nType: {kind}\n\n{purpose}\n\nExample:\n{json.dumps({key:value},indent=2)}")

def handle_when_reference_key_inserted(event: tk.Event) -> None:
    """Add a clicked reference skeleton when the current editor object is valid."""
    selected=widgets["tree"].selection()
    if not selected:return
    data=parse_additional_json()
    if data is None:return
    key=selected[0]
    if key in data: set_status(f'Key "{key}" is already present.'); return
    data[key]=reference[key][2]; replace_editor_json(data); set_status(f"Inserted reference key: {key}."); validate_and_autosave()

def handle_when_user_formats_json() -> None:
    """Pretty-print valid additional JSON and use the normal autosave path."""
    data=parse_additional_json()
    if data is not None: replace_editor_json(data); validate_and_autosave()

def replace_editor_json(data: dict) -> None:
    """Replace editor contents with stable Unicode-preserving formatted JSON."""
    editor=widgets["editor"]; editor.delete("1.0","end"); editor.insert("1.0",json.dumps(data,indent=2,ensure_ascii=False)); editor.edit_modified(False)

def handle_when_user_copies_json() -> None:
    """Copy only valid additional JSON."""
    data=parse_additional_json()
    if data is not None: copy_text(json.dumps(data,indent=2,ensure_ascii=False)); set_status("Copied additional JSON to clipboard.")

def handle_when_user_copies_complete_entry() -> None:
    """Copy a merged full entry only when additional JSON is valid."""
    data=parse_additional_json()
    if data is not None:
        source=widgets["document"]
        complete={"id":source.get("id", ""), "identity":source.get("identity", {})}
        complete.update(data); copy_text(json.dumps(complete,indent=2,ensure_ascii=False)); set_status("Copied complete dictionary entry to clipboard.")

def handle_when_user_uses_full_entry_save_shortcut(event: tk.Event) -> str:
    """Make Ctrl+S validate immediately and keep the shortcut inside this window."""
    validate_and_autosave(); return "break"

def copy_text(text: str) -> None:
    """Copy text through the full editor's owning window."""
    window=widgets["window"]; window.clipboard_clear(); window.clipboard_append(text); window.update()

def set_status(text: str) -> None:
    """Show local status and mirror it into the cockpit status bar."""
    widgets["status"].configure(text=text); g["status-fn"](text)
