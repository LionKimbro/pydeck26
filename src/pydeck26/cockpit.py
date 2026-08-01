"""The first PyDeck cockpit window and its small runtime machine."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

import lionscliapp as app
from lionscliapp import config_io

from pydeck26.project_snapshot import read_project_snapshot


g = {
    "project-root": None,
    "snapshot": None,
    "status": "Choose a project folder to enter its cockpit.",
}
widgets = {}


def launch_cockpit() -> None:
    """Create the hidden Tk runtime anchor and realize the cockpit window."""
    root = tk.Tk()
    root.withdraw()
    app.attach_tk(root, handle_when_lionscliapp_forwards_message)
    realize_main_cockpit_window(root)
    load_configured_project_if_available()
    root.mainloop()


def realize_main_cockpit_window(root: tk.Tk) -> None:
    """Build the singleton visible cockpit window."""
    window = tk.Toplevel(root)
    window.title("PyDeck 26 — Project Cockpit")
    window.geometry("1050x700")
    window.minsize(760, 500)
    window.columnconfigure(0, weight=1)
    window.rowconfigure(2, weight=1)
    widgets["window"] = window

    title = ttk.Label(window, text="PyDeck 26", font=("TkDefaultFont", 20, "bold"))
    title.grid(row=0, column=0, sticky="w", padx=16, pady=(16, 2))
    subtitle = ttk.Label(window, text="Enter a project. See its living territory. Find your way back in.")
    subtitle.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 12))
    build_project_path_panel(window)
    build_project_overview(window)
    build_status_bar(window)
    window.protocol("WM_DELETE_WINDOW", handle_when_user_closes_main_cockpit)


def build_project_path_panel(window: tk.Toplevel) -> None:
    """Create the project-root selection controls."""
    panel = ttk.Frame(window, padding=(16, 0, 16, 12))
    panel.grid(row=2, column=0, sticky="new")
    panel.columnconfigure(1, weight=1)
    ttk.Label(panel, text="Project folder").grid(row=0, column=0, sticky="w", padx=(0, 8))
    entry = ttk.Entry(panel)
    entry.grid(row=0, column=1, sticky="ew")
    entry.bind("<Control-Return>", handle_when_user_accepts_project_path)
    ttk.Button(panel, text="Browse…", command=handle_when_user_clicks_browse_project).grid(row=0, column=2, padx=(8, 0))
    ttk.Button(panel, text="Enter project", command=handle_when_user_clicks_enter_project).grid(row=0, column=3, padx=(8, 0))
    widgets["project-path"] = entry


def build_project_overview(window: tk.Toplevel) -> None:
    """Create the project facts view, which is a projection of the snapshot."""
    panel = ttk.Frame(window, padding=(16, 0, 16, 12))
    panel.grid(row=3, column=0, sticky="nsew")
    window.rowconfigure(3, weight=1)
    panel.columnconfigure(0, weight=1)
    panel.rowconfigure(1, weight=1)
    ttk.Label(panel, text="Project territory", font=("TkDefaultFont", 12, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 6))
    tree = ttk.Treeview(panel, columns=("kind", "state"), show="tree headings")
    tree.heading("#0", text="Location / project fact")
    tree.heading("kind", text="Kind")
    tree.heading("state", text="State")
    tree.column("#0", width=530)
    tree.column("kind", width=130, stretch=False)
    tree.column("state", width=130, stretch=False)
    tree.grid(row=1, column=0, sticky="nsew")
    scrollbar = ttk.Scrollbar(panel, orient="vertical", command=tree.yview)
    scrollbar.grid(row=1, column=1, sticky="ns")
    tree.configure(yscrollcommand=scrollbar.set)
    widgets["overview-tree"] = tree


def build_status_bar(window: tk.Toplevel) -> None:
    """Create the persistent bottom status message area."""
    status = ttk.Label(window, anchor="w", relief="sunken", padding=(8, 4))
    status.grid(row=4, column=0, sticky="ew")
    widgets["status"] = status
    project_status()


def handle_when_user_clicks_browse_project() -> None:
    """Let the user choose a project root, then enter it immediately."""
    selected = filedialog.askdirectory(parent=widgets["window"], title="Choose a Python project folder")
    if selected:
        widgets["project-path"].delete(0, tk.END)
        widgets["project-path"].insert(0, selected)
        enter_project(Path(selected))


def handle_when_user_closes_main_cockpit() -> None:
    """End the Tk runtime when the cockpit's only visible window closes."""
    widgets["window"].master.destroy()


def handle_when_user_clicks_enter_project() -> None:
    """Enter the path currently shown in the project-root field."""
    enter_project(Path(widgets["project-path"].get()))


def handle_when_user_accepts_project_path(event: tk.Event) -> str:
    """Make Ctrl+Enter accept a manually typed project path."""
    handle_when_user_clicks_enter_project()
    return "break"


def handle_when_lionscliapp_forwards_message(message: dict) -> None:
    """Raise the cockpit when LionsCLIApp forwards a later invocation."""
    if message.get("type") == "summon":
        app.bring_window_to_front(widgets["window"])


def load_configured_project_if_available() -> None:
    """Restore the previously entered project if the persistent setting is valid."""
    configured_path = app.ctx["path.project"]
    if configured_path.is_dir():
        widgets["project-path"].insert(0, str(configured_path))
        enter_project(configured_path)


def enter_project(root: Path) -> None:
    """Read one project folder and project its orientation facts into the window."""
    snapshot = read_project_snapshot(root)
    g["project-root"] = root
    g["snapshot"] = snapshot
    widgets["project-path"].delete(0, tk.END)
    widgets["project-path"].insert(0, snapshot["root"])
    project_snapshot()
    if snapshot["exists"]:
        persist_project_root(snapshot["root"])
        g["status"] = f"Entered {snapshot['root']}. This setting will persist for the next launch."
    else:
        g["status"] = snapshot["problems"][0]
    project_status()


def project_snapshot() -> None:
    """Reconcile the facts tree with the current project snapshot."""
    tree = widgets["overview-tree"]
    tree.delete(*tree.get_children())
    snapshot = g["snapshot"]
    if not snapshot["exists"]:
        tree.insert("", "end", text="No project loaded", values=("", "missing"))
        return

    identity = snapshot["identity"]
    tree.insert("", "end", text=f"Name: {identity.get('name', 'unknown')}", values=("Zoo identity", identity.get("repo-type", "untyped")))
    for marker in snapshot["markers"]:
        state = "present" if marker["exists"] else "not present"
        tree.insert("", "end", text=marker["name"], values=(marker["kind"], state))
    raw_parent = tree.insert("", "end", text="docs/raw", values=("project memory", f"{len(snapshot['raw_documents'])} documents"), open=True)
    for name in snapshot["raw_documents"]:
        tree.insert(raw_parent, "end", text=name, values=("raw document", "preserved"))
    for problem in snapshot["problems"]:
        tree.insert("", "end", text=problem, values=("warning", "check"))


def project_status() -> None:
    """Project the current runtime status message."""
    widgets["status"].configure(text=g["status"])


def persist_project_root(path: str) -> None:
    """Persist the cockpit's selected root through LionsCLIApp's config store."""
    config_io.raw_config["options"]["path.project"] = path
    config_io.write_config()
    app.ctx["path.project"] = Path(path)
