"""LionsCLIApp entrypoint for the PyDeck 26 cockpit."""

from __future__ import annotations

import lionscliapp as app

from pydeck26.cockpit import launch_cockpit


def main() -> None:
    """Declare the application before handing command dispatch to LionsCLIApp."""
    app.declare_app("pydeck26", "0.1.0")
    app.describe_app("A persistent cockpit for entering and understanding python-2026-03 projects.")
    app.declare_projectdir(".pydeck26")
    app.set_flag("uses_tkinter", True)
    app.declare_key("path.project", "")
    app.describe_key("path.project", "The project folder currently held by the cockpit.")
    app.declare_cmd("", launch_cockpit)
    app.set_cmd_flag("", "tkinter", True)
    app.set_cmd_flag("", "single_instance", True)
    app.main()
