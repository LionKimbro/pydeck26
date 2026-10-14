"""Disk machine: the GUI application's sole filesystem boundary."""

from . import machine, mobile_stacks as ms, storage
from .project_snapshot import read_project_snapshot

g = {"project-root": None}  # Installed before workers start; fixed for the process.


def read_project_bundle():
    root = g["project-root"]
    initialized = storage.is_initialized(root)
    return {
        "snapshot": read_project_snapshot(root),
        "initialized": initialized,
        "whiteboard": storage.load_whiteboard(root) if initialized else "",
        "dictionary": storage.load_dictionary_entry(root),
        "conversations": storage.load_conversations(root),
        "ideas": storage.load_ideas(root),
        "resources": storage.load_resources(root),
        "history": storage.list_snapshots(root),
    }


def handle_when_disk_loads_bound_project():
    if ms.get_register("initialize"):
        storage.initialize_project(g["project-root"])
    ms.set_register(("bundle", read_project_bundle()))


def handle_when_disk_writes_project_documents():
    writers = {
        "whiteboard": storage.save_whiteboard,
        "dictionary": storage.save_dictionary_entry,
        "conversations": storage.save_conversations,
        "ideas": storage.save_ideas,
        "resources": storage.save_resources,
    }
    for key, value in ms.get_register("documents").items():
        writers[key](g["project-root"], value)


def handle_when_disk_reads_whiteboard_history():
    ms.set_register(("text", storage.read_snapshot(ms.get_register("path"))))


def handle_when_disk_creates_whiteboard_snapshot():
    try:
        storage.save_snapshot(g["project-root"], ms.get_register("text"))
    except FileExistsError:
        ms.set_register(("error", "A snapshot already exists for this second. Please try again."))
    else:
        ms.set_register(("error", None))
    ms.set_register(("history", storage.list_snapshots(g["project-root"])))


def handle_when_disk_resolves_resource_path():
    item = ms.get_register("item")
    root = g["project-root"].resolve()
    path = (root / item.get("path", "") / item.get("filename", "")).resolve()
    error = None
    if ms.get_register("action") == "OPEN_PATH":
        if not path.is_relative_to(root):
            error = "Resource path must remain inside this project."
        elif not path.exists():
            error = "This resource is not currently on disk."
    ms.set_register(("path", str(path)))
    ms.set_register(("error", error))


def handle_when_disk_resolves_structure_paths():
    root = g["project-root"].resolve()
    ms.set_register(("items", [
        {"path": item.get("path", ""), "filename": item.get("filename", ""),
         "full-path": str((root / item.get("path", "") / item.get("filename", "")).resolve()),
         "hook": item.get("hook", "")}
        for item in ms.get_register("items")
    ]))


HANDLERS = {
    "LOAD_PROJECT": handle_when_disk_loads_bound_project,
    "WRITE_DOCUMENTS": handle_when_disk_writes_project_documents,
    "READ_HISTORY": handle_when_disk_reads_whiteboard_history,
    "SNAPSHOT": handle_when_disk_creates_whiteboard_snapshot,
    "RESOURCE_PATH": handle_when_disk_resolves_resource_path,
    "STRUCTURE_PATHS": handle_when_disk_resolves_structure_paths,
}
