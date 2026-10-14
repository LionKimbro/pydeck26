"""Composition of the Tk, Core, Mem, and Disk machines."""

from pathlib import Path
from queue import Queue

from . import core, disk, image, machine, mem


def start_project_workers(project_root):
    """Wire a fixed project root and start the supervised project/image workers."""
    machine.initialize_machine_system()
    disk.g["project-root"] = Path(project_root).resolve()
    mem.documents.clear()
    mem.g.update({"revision": 0, "initialized": False})
    commands = Queue()
    for name, handlers in (("CORE", core.HANDLERS), ("MEM", mem.HANDLERS), ("DISK", disk.HANDLERS), ("IMAGE", image.HANDLERS)):
        machine.install_machine({"name": name, "handlers": handlers})
    machine.machines["CORE"]["commands"] = commands
    machine.start_worker("DISK", machine.run_machine)
    machine.start_worker("MEM", machine.run_machine)
    machine.start_worker("IMAGE", machine.run_machine)
    machine.start_worker("CORE", core.run_reducer_core)
    return commands


def finish_worker_shutdown():
    """Stop producers before Disk; ordinary close has already confirmed writes."""
    machine.join_machine("CORE")
    machine.machines["IMAGE"]["inbox"].put(None)
    machine.join_machine("IMAGE")
    machine.join_machine("MEM")
    machine.machines["DISK"]["inbox"].put(None)
    machine.join_machine("DISK")


def run_project(project_root, root=None):
    # Import the presentation machine only for GUI execution.
    from tkinterdnd2 import TkinterDnD
    import lionscliapp as app
    from . import tk as cockpit

    own_root = root is None
    root = TkinterDnD.Tk() if own_root else root
    if not own_root:
        root.TkdndVersion = TkinterDnD._require(root)
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
