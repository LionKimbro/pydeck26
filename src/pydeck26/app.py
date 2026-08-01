"""LionsCLIApp entrypoint for the PyDeck 26 cockpit."""

from __future__ import annotations

import lionscliapp as app
from lionscliapp.execroot import get_execroot

from pydeck26.cockpit import launch_cockpit
from pydeck26.storage import initialize_project


def main() -> None:
    """Declare the application before handing command dispatch to LionsCLIApp."""
    app.declare_app("pydeck26", "0.1.0")
    app.describe_app("A persistent cockpit for entering and understanding python-2026-03 projects.")
    app.declare_projectdir(".pydeck26")
    app.set_flag("uses_tkinter", True)
    app.declare_cmd("", launch_cockpit)
    app.set_cmd_flag("", "tkinter", True)
    app.set_cmd_flag("", "single_instance", True)
    app.declare_cmd("init", initialize_bound_project)
    app.describe_cmd("init", "Initialize PyDeck-owned Whiteboard storage in this project.")
    app.main()


def initialize_bound_project() -> None:
    """Initialize the project bound to this command invocation."""
    initialize_project(get_execroot())
    print(f"Initialized PyDeck 26 in {get_execroot()}")
