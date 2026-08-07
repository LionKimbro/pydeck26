"""Small editor dialog for one curated Structure resource."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


g = {"on-save": None}
widgets = {}


def set_resource_save_handler(fn) -> None:
    """Install the cockpit boundary that receives one resource record."""
    g["on-save"] = fn


def open_resource_editor(details: dict) -> None:
    """Open a small editor for a new resource or its explanatory hook."""
    window = tk.Toplevel(details["parent"])
    window.title(details["title"])
    window.resizable(False, False)
    window.columnconfigure(1, weight=1)
    fields = {}
    for row, key, label in [(0, "path", "Path"), (1, "filename", "Filename"), (2, "hook", "Hook")]:
        ttk.Label(window, text=label).grid(row=row, column=0, sticky="w", padx=(12, 6), pady=5)
        entry = ttk.Entry(window, width=58)
        entry.grid(row=row, column=1, sticky="ew", padx=(0, 12), pady=5)
        entry.insert(0, details["item"].get(key, ""))
        fields[key] = entry
    if details["hook-only"]:
        fields["path"].configure(state="readonly")
        fields["filename"].configure(state="readonly")
    buttons = ttk.Frame(window)
    buttons.grid(row=3, column=0, columnspan=2, sticky="e", padx=12, pady=(7, 12))
    ttk.Button(buttons, text="Cancel", command=window.destroy).pack(side="left", padx=(0, 6))
    ttk.Button(buttons, text="Save", command=handle_when_user_saves_resource).pack(side="left")
    widgets.update({"window": window, "fields": fields, "item": details["item"]})
    window.bind("<Control-Return>", handle_when_user_uses_resource_save_shortcut)
    fields["hook" if details["hook-only"] else "path"].focus_set()
    window.grab_set()


def handle_when_user_saves_resource() -> None:
    """Return the edited coherent resource record to the owning cockpit."""
    fields = widgets["fields"]
    item = dict(widgets["item"])
    item.update({key: fields[key].get().strip() for key in ["path", "filename", "hook"]})
    g["on-save"](item)
    widgets["window"].destroy()


def handle_when_user_uses_resource_save_shortcut(event: tk.Event) -> str:
    """Save the resource dialog with Ctrl+Enter."""
    handle_when_user_saves_resource()
    return "break"
