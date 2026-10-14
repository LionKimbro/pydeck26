"""Real-worker tests for ownership, asynchronous saves, and lifecycle barriers."""

import json
from queue import Empty
from threading import Event, current_thread
from time import monotonic

import pytest

from pydeck26 import core, disk, machine, main, mem, mobile_stacks, workspace
from pydeck26.storage import initialize_project, load_whiteboard


def receive(commands, predicate):
    deadline = monotonic() + 5
    while monotonic() < deadline:
        if machine.fatal.is_set():
            pytest.fail("a worker failed unexpectedly")
        try:
            command = commands.get(timeout=0.05)
        except Empty:
            continue
        if predicate(command):
            return command
    pytest.fail("timed out waiting for a machine command")


def state(commands, predicate=lambda view: True):
    return receive(commands, lambda item: item["type"] == "STATE" and predicate(item))


def send(event):
    machine.machines["CORE"]["inbox"].put(event)


def stop(commands):
    send({"type": "SHUTDOWN"})
    receive(commands, lambda item: item["type"] == "SHUTDOWN_COMPLETE")
    finish()


def finish():
    # Assert termination with a deadline before calling the production joins.
    for name in ("CORE", "MEM"):
        machine.machines[name]["thread"].join(5)
        assert not machine.machines[name]["thread"].is_alive()
    machine.machines["DISK"]["inbox"].put(None)
    machine.machines["DISK"]["thread"].join(5)
    assert not machine.machines["DISK"]["thread"].is_alive()
    main.finish_worker_shutdown()
    assert all(runtime["lifecycle"] == "reaped" for runtime in machine.machines.values())


@pytest.fixture
def project(tmp_path):
    initialize_project(tmp_path)
    commands = main.start_project_workers(tmp_path)
    state(commands, lambda view: view["ready"])
    yield tmp_path, commands
    if any(runtime["thread"].is_alive() for runtime in machine.machines.values()):
        if not machine.fatal.is_set():
            stop(commands)
        else:
            finish()


def test_edits_stay_working_until_save_and_views_are_copies(project):
    root, commands = project
    send({"type": "WHITEBOARD_EDIT", "text": "working"})
    view = state(commands, lambda view: view["view-text"] == "working")
    assert load_whiteboard(root) == ""
    assert mem.documents["whiteboard"] == ""
    view["documents"]["resources"]["items"].append({"filename": "not shared"})
    assert core.documents["resources"]["items"] == []
    send({"type": "SAVE"})
    state(commands, lambda view: view["status"] == "Project state saved.")
    assert load_whiteboard(root) == "working"
    assert mem.documents["whiteboard"] == "working"


def test_edit_during_held_disk_write_survives_close(project, monkeypatch):
    root, commands = project
    started, release = Event(), Event()
    original = disk.HANDLERS["WRITE_DOCUMENTS"]

    def held_write():
        started.set()
        assert release.wait(5)
        original()

    monkeypatch.setitem(disk.HANDLERS, "WRITE_DOCUMENTS", held_write)
    send({"type": "WHITEBOARD_EDIT", "text": "first"})
    send({"type": "SAVE"})
    assert started.wait(5)
    send({"type": "WHITEBOARD_EDIT", "text": "second"})
    state(commands, lambda view: view["view-text"] == "second")
    assert mem.documents["whiteboard"] == "first"
    assert load_whiteboard(root) == ""
    send({"type": "SHUTDOWN"})
    # No successful save or shutdown may be published while Disk is held.
    pending = []
    while not commands.empty():
        pending.append(commands.get_nowait())
    assert not any(item["type"] == "SHUTDOWN_COMPLETE" for item in pending)
    release.set()
    receive(commands, lambda item: item["type"] == "SHUTDOWN_COMPLETE")
    finish()
    assert load_whiteboard(root) == "second"


def test_dialog_events_use_record_identity_and_preserve_extensions(project):
    root, commands = project
    send({"type": "NEW_CONVERSATION"})
    first = state(commands, lambda view: len(view["documents"]["conversations"]["items"]) == 1)
    first_id = first["selected-conversation-id"]
    send({"type": "NEW_CONVERSATION"})
    second = state(commands, lambda view: len(view["documents"]["conversations"]["items"]) == 2)
    second_id = second["selected-conversation-id"]
    send({"type": "CONVERSATION_EDIT", "id": first_id,
          "fields": {"description": "first dialog", "extension": {"keep": True}}})
    send({"type": "DICTIONARY_ADDITIONAL", "additional": {"custom": ["keep"]}})
    send({"type": "DICTIONARY_EDIT", "identity": {"title": "New title"}})
    stop(commands)
    data = json.loads((root / "db/pydeck26/conversations.json").read_text())
    first = next(item for item in data["items"] if item["id"] == first_id)
    second = next(item for item in data["items"] if item["id"] == second_id)
    assert first["description"] == "first dialog"
    assert first["extension"] == {"keep": True}
    assert second["description"] == ""
    dictionary = json.loads((root / "db/pydeck26/dictionary-entry.json").read_text())
    assert dictionary["custom"] == ["keep"]
    assert dictionary["identity"]["title"] == "New title"


def test_stale_history_read_does_not_replace_newer_edit(project, monkeypatch):
    root, commands = project
    send({"type": "WHITEBOARD_EDIT", "text": "snapshot text"})
    send({"type": "SNAPSHOT"})
    state(commands, lambda view: view["history-count"] == 1)
    started, release = Event(), Event()
    original = disk.HANDLERS["READ_HISTORY"]

    def held_read():
        started.set()
        assert release.wait(5)
        original()

    monkeypatch.setitem(disk.HANDLERS, "READ_HISTORY", held_read)
    send({"type": "HISTORY_SELECT", "index": 1})
    assert started.wait(5)
    send({"type": "WHITEBOARD_EDIT", "text": "newer edit"})
    state(commands, lambda view: view["view-text"] == "newer edit")
    release.set()
    stop(commands)
    assert load_whiteboard(root) == "newer edit"


def test_editing_history_preserves_previous_current_as_virtual(project):
    root, commands = project
    send({"type": "WHITEBOARD_EDIT", "text": "history"})
    send({"type": "SNAPSHOT"})
    state(commands, lambda view: view["history-count"] == 1)
    send({"type": "WHITEBOARD_EDIT", "text": "present"})
    send({"type": "HISTORY_SELECT", "index": 1})
    state(commands, lambda view: view["view-index"] == 1)
    send({"type": "WHITEBOARD_EDIT", "text": "history edited"})
    view = state(commands, lambda view: view["view-text"] == "history edited")
    assert view["history-count"] == 2
    send({"type": "HISTORY_SELECT", "index": 1})
    state(commands, lambda view: view["view-text"] == "present")
    stop(commands)
    assert load_whiteboard(root) == "history edited"
    assert next((root / "docs/whiteboard").iterdir()).read_text() == "history"


def test_initialize_after_unsaved_dictionary_edit_keeps_draft(tmp_path):
    commands = main.start_project_workers(tmp_path)
    state(commands, lambda view: view["ready"])
    assert not (tmp_path / "db").exists()
    send({"type": "DICTIONARY_EDIT", "identity": {"title": "Draft before init"}})
    send({"type": "INITIALIZE"})
    state(commands, lambda view: view["initialized"])
    stop(commands)
    data = json.loads((tmp_path / "db/pydeck26/dictionary-entry.json").read_text())
    assert data["identity"]["title"] == "Draft before init"


@pytest.mark.parametrize("name,entry", [("CORE", "COMMIT_RETURNED"),
                                        ("MEM", "COMMIT_PROJECT"),
                                        ("DISK", "WRITE_DOCUMENTS")])
def test_unexpected_worker_failure_stops_all_workers(tmp_path, monkeypatch, name, entry):
    initialize_project(tmp_path)
    module = {"CORE": core, "MEM": mem, "DISK": disk}[name]

    def fail():
        raise RuntimeError("injected failure")

    monkeypatch.setitem(module.HANDLERS, entry, fail)
    commands = main.start_project_workers(tmp_path)
    state(commands, lambda view: view["ready"])
    send({"type": "SAVE"})
    assert machine.fatal.wait(5)
    finish()


def test_mobile_stack_publication_transfers_ownership():
    machine.initialize_machine_system()
    machine.install_machine({"name": "MEM", "handlers": {}})
    machine.install_machine({"name": "CORE", "handlers": {}})
    machine.claim_machine("MEM")
    mobile_stacks.create_stack()
    mobile_stacks.set_register(("nested", {"values": [1]}))
    mobile_stacks.push_frame({"machine": "CORE", "entry": "RETURN"})
    work = mobile_stacks.stack()
    machine.route_current_stack()
    assert mobile_stacks.stack() is None
    assert machine.machines["CORE"]["inbox"].get_nowait() is work


def test_gui_filesystem_reads_and_writes_run_on_disk(tmp_path, monkeypatch):
    initialize_project(tmp_path)
    readers = []
    original = disk.read_project_bundle

    def observed_read():
        readers.append(current_thread().name)
        return original()

    monkeypatch.setattr(disk, "read_project_bundle", observed_read)
    commands = main.start_project_workers(tmp_path)
    state(commands, lambda view: view["ready"])
    stop(commands)
    assert readers == ["PyDeck DISK"]


def test_resources_and_ideas_keep_order_unknown_fields_and_original_files(project):
    root, commands = project
    source = root / "README.md"
    source.write_text("leave this alone", encoding="utf-8")
    send({"type": "RESOURCE_ADD", "path": str(source), "kind": "file"})
    send({"type": "RESOURCE_ADD", "path": str(root / "docs"), "kind": "folder"})
    send({"type": "RESOURCE_MOVE", "index": 1, "change": -1})
    send({"type": "RESOURCE_EDIT", "index": 0, "item": {"hook": "project history", "custom": True}})
    send({"type": "IDEA_SAVE", "item": {"guid": "idea", "title": "First", "pinned": True, "custom": [1]}})
    send({"type": "IDEA_SAVE", "item": {"guid": "idea", "title": "Revised", "pinned": False}})
    stop(commands)
    resources = json.loads((root / "db/pydeck26/resources.json").read_text())
    assert [item["filename"] for item in resources["items"]] == ["docs", "README.md"]
    assert resources["items"][0]["custom"] is True
    assert source.read_text() == "leave this alone"
    ideas = json.loads((root / "db/ideas.json").read_text())
    assert ideas["items"] == [{"guid": "idea", "title": "Revised", "pinned": False, "custom": [1]}]


def test_copy_structure_exports_ordered_paths_without_changing_records(project):
    root, commands = project
    send({"type": "COPY_STRUCTURE"})
    assert json.loads(receive(commands, lambda command: command["type"] == "COPY_TEXT")["text"]) == []
    for path, kind in [(root / "missing.txt", "file"), (root / "docs", "folder"),
                       (root.parent / "outside.txt", "file")]:
        send({"type": "RESOURCE_ADD", "path": str(path), "kind": kind})
    send({"type": "RESOURCE_MOVE", "index": 1, "change": -1})
    send({"type": "RESOURCE_EDIT", "index": 0, "item": {"hook": "文書", "custom": True}})
    send({"type": "COPY_STRUCTURE"})
    copied = receive(commands, lambda command: command["type"] == "COPY_TEXT")["text"]
    assert "文書" in copied
    assert json.loads(copied) == [
        {"path": "", "filename": "docs", "full-path": str(root / "docs"), "hook": "文書"},
        {"path": "", "filename": "missing.txt", "full-path": str(root / "missing.txt"),
         "hook": "(double-click to assign hook)"},
        {"path": str(root.parent), "filename": "outside.txt",
         "full-path": str(root.parent / "outside.txt"), "hook": "(double-click to assign hook)"},
    ]
    stop(commands)
    saved = json.loads((root / "db/pydeck26/resources.json").read_text())
    assert saved["items"][0]["custom"] is True
    assert all("full-path" not in item for item in saved["items"])


def test_close_waits_for_outstanding_snapshot_work(project, monkeypatch):
    root, commands = project
    started, release = Event(), Event()
    original = disk.HANDLERS["SNAPSHOT"]

    def held_snapshot():
        started.set()
        assert release.wait(5)
        original()

    monkeypatch.setitem(disk.HANDLERS, "SNAPSHOT", held_snapshot)
    send({"type": "WHITEBOARD_EDIT", "text": "retained"})
    send({"type": "SNAPSHOT"})
    assert started.wait(5)
    send({"type": "SHUTDOWN"})
    release.set()
    receive(commands, lambda item: item["type"] == "SHUTDOWN_COMPLETE")
    finish()
    assert next((root / "docs/whiteboard").iterdir()).read_text() == "retained"


def test_resource_open_rejects_path_outside_project(project):
    root, commands = project
    send({"type": "RESOURCE_ACTION", "item": {"path": "..", "filename": "outside"}, "action": "OPEN_PATH"})
    state(commands, lambda view: view["status"] == "Resource path must remain inside this project.")
    stop(commands)


def test_workspace_roundtrip_preserves_notes_layout_and_existing_project_files(project):
    root, commands = project
    source_paths = [root / "db/pydeck26" / name for name in ("dictionary-entry.json", "resources.json", "conversations.json")]
    original_files = {path: path.read_bytes() if path.exists() else None for path in source_paths}
    send({"type": "CREATE_TAB", "label": "Workbench"})
    view = state(commands, lambda view: view["documents"]["workspace"]["selected-tab-id"] != "cockpit")
    document = view["documents"]["workspace"]
    tab_id = document["selected-tab-id"]
    row_id = workspace.get_tab(document, tab_id)["row-ids"][0]
    send({"type": "SET_ROW_COLUMNS", "row-id": row_id, "column-count": 3})
    send({"type": "HOST_PANEL", "position-id": workspace.position_id(row_id, 1), "panel-id": "project-whiteboard"})
    send({"type": "CREATE_NOTES", "position-id": workspace.position_id(row_id, 2)})
    view = state(commands, lambda view: view["documents"]["workspace"]["positions"].get(workspace.position_id(row_id, 2), {}).get("panel-id") is not None)
    panel_id = view["documents"]["workspace"]["positions"][workspace.position_id(row_id, 2)]["panel-id"]
    send({"type": "NOTES_EDIT", "panel-id": panel_id, "text": "independent writing"})
    send({"type": "SET_ROW_HEIGHT", "row-id": row_id, "height": 380})
    send({"type": "SET_SASH_PROPORTIONS", "row-id": row_id, "proportions": [0.2, 0.65]})
    stop(commands)

    stored = json.loads((root / "db/pydeck26/workspace.json").read_text())
    assert stored["rows"][row_id]["height"] == 380
    assert stored["rows"][row_id]["sash-proportions"] == [0.2, 0.65]
    assert stored["panels"][panel_id]["text"] == "independent writing"
    assert all((path.read_bytes() if path.exists() else None) == original for path, original in original_files.items())
    commands = main.start_project_workers(root)
    restored = state(commands, lambda view: view["ready"])
    assert restored["documents"]["workspace"] == stored
    restored["documents"]["workspace"]["panels"][panel_id]["text"] = "not shared"
    assert mem.documents["workspace"]["panels"][panel_id]["text"] == "independent writing"
    stop(commands)



def test_delete_during_save_cannot_resurrect_a_panel(project, monkeypatch):
    root, commands = project
    send({"type": "CREATE_NOTES", "position-id": "overview/column-1"})
    view = state(commands, lambda view: view["status"] == "Project state saved.")
    panel_id = view["documents"]["workspace"]["positions"]["overview/column-1"]["panel-id"]
    started, release = Event(), Event()
    original = disk.HANDLERS["WRITE_DOCUMENTS"]

    def held_write():
        started.set()
        assert release.wait(5)
        original()

    monkeypatch.setitem(disk.HANDLERS, "WRITE_DOCUMENTS", held_write)
    send({"type": "NOTES_EDIT", "panel-id": panel_id, "text": "in flight"})
    send({"type": "SAVE"})
    assert started.wait(5)
    send({"type": "DELETE_PANEL", "panel-id": panel_id})
    state(commands, lambda view: panel_id not in view["documents"]["workspace"]["panels"])
    send({"type": "NOTES_EDIT", "panel-id": panel_id, "text": "obsolete draft"})
    release.set()
    stop(commands)
    stored = json.loads((root / "db/pydeck26/workspace.json").read_text())
    assert panel_id not in stored["panels"]
    commands = main.start_project_workers(root)
    view = state(commands, lambda view: view["ready"])
    assert panel_id not in view["documents"]["workspace"]["panels"]
    stop(commands)
