"""Tk-owned Sweeper capture form; submission and file writes travel via Core."""

import tkinter as tk
from tkinter import ttk
from uuid import uuid4

from .theme import COLORS

g = {"dialog": None, "send": None, "tab-id": None, "token": None}
widgets = {}
DIRECTIVES = {
    "Go ahead": "go-ahead",
    "Please investigate": "please-investigate",
    "Please hold": "please-hold",
}


def show_form(context):
    if g["dialog"] is not None:
        try:
            if g["dialog"].winfo_exists():
                g["dialog"].lift()
                return
        except tk.TclError:
            pass
    dialog = tk.Toplevel(context["window"])
    g.update({"dialog": dialog, "send": context["send"],
              "tab-id": context["tab-id"], "token": None})
    widgets.clear()
    dialog.title("New Sweeper request")
    dialog.transient(context["window"])
    dialog.geometry("640x480")
    dialog.minsize(420, 340)
    dialog.columnconfigure(0, weight=1)
    dialog.rowconfigure(0, weight=1)
    frame = ttk.Frame(dialog, padding=12)
    frame.grid(sticky="nsew")
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(4, weight=1)
    ttk.Label(frame, text=f"Project: {context['project-root']}", wraplength=580).grid(
        row=0, column=0, sticky="w", pady=(0, 10))
    ttk.Label(frame, text="Title").grid(row=1, column=0, sticky="w")
    title = ttk.Entry(frame)
    title.grid(row=2, column=0, sticky="ew", pady=(2, 8))
    ttk.Label(frame, text="Description").grid(row=3, column=0, sticky="w")
    body_frame = ttk.Frame(frame)
    body_frame.grid(row=4, column=0, sticky="nsew", pady=(2, 8))
    body_frame.rowconfigure(0, weight=1)
    body_frame.columnconfigure(0, weight=1)
    description = tk.Text(body_frame, wrap="word", height=10, undo=True)
    description.grid(row=0, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(body_frame, command=description.yview)
    scroll.grid(row=0, column=1, sticky="ns")
    description.configure(yscrollcommand=scroll.set)
    choices = ttk.Frame(frame)
    choices.grid(row=5, column=0, sticky="ew")
    ttk.Label(choices, text="Directive:").pack(side="left", padx=(0, 8))
    directive = ttk.Combobox(choices, values=list(DIRECTIVES), state="readonly", width=24)
    directive.set("Go ahead")
    directive.pack(side="left")
    status = ttk.Label(frame, foreground=COLORS["danger"], wraplength=580)
    status.grid(row=6, column=0, sticky="ew", pady=8)
    actions = ttk.Frame(frame)
    actions.grid(row=7, column=0, sticky="e")
    cancel = ttk.Button(actions, text="Cancel", command=handle_when_user_closes_form)
    cancel.pack(side="left", padx=6)
    save = ttk.Button(actions, text="Save request", command=handle_when_user_saves_request)
    save.pack(side="left")
    widgets.update({"title": title, "description": description, "directive": directive,
                    "status": status, "save": save, "cancel": cancel})
    dialog.protocol("WM_DELETE_WINDOW", handle_when_user_closes_form)
    dialog.bind("<Escape>", lambda event: handle_when_user_closes_form())
    title.focus_set()


def handle_when_user_closes_form():
    if g["token"] is None and g["dialog"] is not None:
        g["dialog"].destroy()
        g["dialog"] = None
        widgets.clear()


def handle_when_user_saves_request():
    if g["token"] is not None:
        return
    title = widgets["title"].get().strip()
    description = widgets["description"].get("1.0", "end-1c").strip()
    if not title or not description:
        widgets["status"].configure(text="Please enter both a title and a description.")
        widgets["title" if not title else "description"].focus_set()
        return
    g["token"] = str(uuid4())
    widgets["status"].configure(text="Saving request…")
    for key in ("save", "cancel", "title"):
        widgets[key].state(["disabled"])
    widgets["description"].configure(state="disabled")
    widgets["directive"].state(["disabled"])
    g["send"]({"type": "SWEEPER_REQUEST", "token": g["token"], "tab-id": g["tab-id"],
               "request": {"title": title, "description": description,
                           "directive": DIRECTIVES[widgets["directive"].get()]}})


def apply_result(command):
    if command["token"] != g["token"] or g["dialog"] is None:
        return
    g["token"] = None
    if not command["error"]:
        handle_when_user_closes_form()
        return
    widgets["status"].configure(text=command["error"])
    for key in ("save", "cancel", "title"):
        widgets[key].state(["!disabled"])
    widgets["description"].configure(state="normal")
    widgets["directive"].state(["!disabled", "readonly"])
