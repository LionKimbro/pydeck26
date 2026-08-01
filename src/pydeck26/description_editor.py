"""A small, cancel-safe editor window for one conversation description."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


g = {
    "on-save": None,
}
widgets = {}


def set_description_save_handler(fn) -> None:
    """Install the parent cockpit's one-argument description save boundary."""
    g["on-save"] = fn


def open_description_editor(details: dict) -> None:
    """Open a temporary editor whose close button cancels uncommitted changes."""
    window = tk.Toplevel(details["parent"])
    window.title(f"{details['date']} — {details['title']}")
    window.geometry("620x360")
    window.minsize(420, 240)
    window.columnconfigure(0, weight=1)
    window.rowconfigure(0, weight=1)
    editor = tk.Text(window, wrap="word", font=("TkFixedFont", 11), padx=10, pady=10)
    editor.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
    editor.insert("1.0", details["description"])
    editor.bind("<Control-Return>", handle_when_user_uses_description_save_shortcut)
    ttk.Button(window, text="Save", command=handle_when_user_saves_description).grid(row=1, column=0, sticky="e", padx=10, pady=(0, 10))
    window.protocol("WM_DELETE_WINDOW", handle_when_user_cancels_description_edit)
    widgets["window"] = window
    widgets["editor"] = editor
    window.grab_set()
    editor.focus_set()


def handle_when_user_saves_description() -> None:
    """Commit the dialog text through the parent handler, then close the dialog."""
    g["on-save"](widgets["editor"].get("1.0", "end-1c"))
    widgets["window"].destroy()


def handle_when_user_uses_description_save_shortcut(event: tk.Event) -> str:
    """Save and close on Ctrl+Enter without placing a newline in the Text area."""
    handle_when_user_saves_description()
    return "break"


def handle_when_user_cancels_description_edit() -> None:
    """Discard dialog-local edits without touching the conversation register."""
    widgets["window"].destroy()
