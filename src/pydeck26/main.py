"""Composition of the Tk, Core, Mem, and Disk machines."""

from pathlib import Path
from queue import Queue

from . import core, disk, machine, mem


def start_project_workers(project_root):
    """Wire a fixed project root and start the three supervised workers."""
    machine.initialize_machine_system()
    disk.g["project-root"] = Path(project_root).resolve()
    mem.documents.clear()
    mem.g.update({"revision": 0, "initialized": False})
    commands = Queue()
    for name, handlers in (("CORE", core.HANDLERS), ("MEM", mem.HANDLERS), ("DISK", disk.HANDLERS)):
        machine.install_machine({"name": name, "handlers": handlers})
    machine.machines["CORE"]["commands"] = commands
    machine.start_worker("DISK", machine.run_machine)
    machine.start_worker("MEM", machine.run_machine)
    machine.start_worker("CORE", core.run_reducer_core)
    return commands


def finish_worker_shutdown():
    """Stop producers before Disk; ordinary close has already confirmed writes."""
    machine.join_machine("CORE")
    machine.join_machine("MEM")
    machine.machines["DISK"]["inbox"].put(None)
    machine.join_machine("DISK")


def run_project(project_root, root=None):
    # Import the presentation machine only for GUI execution.
    import tkinter as tk
    import lionscliapp as app
    from . import tk as cockpit

    own_root = root is None
    root = tk.Tk() if own_root else root
    root.withdraw()
    if own_root:
        app.attach_tk(root, cockpit.handle_when_lionscliapp_forwards_message)
    cockpit.initialize_tk_state(project_root)
    cockpit.realize_main_cockpit_window(root)
    cockpit.g["commands"] = start_project_workers(project_root)
    cockpit.handle_when_polling_core_commands()
    try:
        root.mainloop()
    finally:
        # Also handles external root destruction and GUI callback failures.
        if not machine.fatal.is_set():
            machine.machines["CORE"]["inbox"].put({"type": "SHUTDOWN"})
        finish_worker_shutdown()
    if machine.fatal.is_set():
        raise SystemExit(1)
