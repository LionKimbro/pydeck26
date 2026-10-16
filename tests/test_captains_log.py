"""LSF fidelity, shadowing, Save Over, and durable Core/Mem/Disk acceptance."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from queue import Empty
from threading import Event, current_thread
from time import monotonic
from uuid import uuid4

import lsf
import pytest

from pydeck26 import captains_log as log, captains_log_core, core, disk, machine, main, mem, storage, workspace

MOMENT = datetime(2026, 10, 15, 19, 42, 8, tzinfo=timezone.utc)


def fields(body="A note.", **changes):
    return {"hook": "", "tags": "design captain-log", "major": False, "body": body, **changes}


def create(document, content=None):
    return log.save_entry(document, {"moment": MOMENT, "fields": content or fields()})["entry"]


def test_indented_lsf_roundtrip_preserves_delimiters_blank_lines_and_extensions():
    document = log.make_document()
    document["sections"][0][lsf.KEYS]["custom"] = "header metadata"
    body = "  Already indented\n\n== This is note text ==\n\nLast line\n"
    entry = create(document, fields(body))
    document["sections"][1][lsf.KEYS]["custom"] = "preserve me"
    serialized = log.save_text(document)
    assert "\n  == This is note text ==\n" in serialized
    assert "\n  \n" in serialized
    assert "indent: 2\n" in serialized
    loaded = log.load_text(serialized)
    assert len(loaded["sections"]) == 2
    assert log.get_current_entries(loaded) == [entry]
    assert loaded["sections"][0][lsf.KEYS]["custom"] == "header metadata"
    assert loaded["sections"][1][lsf.KEYS]["custom"] == "preserve me"
    assert log.save_text(loaded) == serialized


def test_revisions_shadow_and_save_over_preserves_identity_and_chain():
    document = log.make_document()
    original = create(document)
    document["sections"][1][lsf.KEYS]["custom"] = "retained"
    first_section = deepcopy(document["sections"][1])
    revision = log.save_entry(document, {"guid": original["guid"], "expected": original,
        "fields": fields("Updated", major=True), "moment": MOMENT + timedelta(days=1)})["entry"]
    assert revision["guid"] != original["guid"]
    assert revision["date"] == original["date"] and revision["time"] == original["time"]
    assert revision["supersedes"] == original["guid"] and revision["modified-on"]
    assert document["sections"][1] == first_section
    assert log.get_current_entries(document) == [revision]
    count = len(document["sections"])
    replaced = log.save_entry(document, {"guid": revision["guid"], "expected": revision,
        "fields": fields("Replaced", major=True), "overwrite": True, "moment": MOMENT + timedelta(days=2)})["entry"]
    assert len(document["sections"]) == count
    assert replaced["guid"] == revision["guid"]
    assert replaced["supersedes"] == original["guid"] and replaced["modified-on"] is None
    assert log.get_current_entries(document) == [replaced]
    assert document["sections"][2][lsf.KEYS]["custom"] == "retained"
    assert document["sections"][1] == first_section


def test_same_second_creations_are_ignored_but_revisions_are_allowed():
    document = log.make_document()
    original = create(document)
    duplicate = log.save_entry(document, {"moment": MOMENT, "fields": fields("Double click")})
    assert duplicate == {"entry": None, "changed": False}
    revision = log.save_entry(document, {"moment": MOMENT, "guid": original["guid"],
        "expected": original, "fields": fields("Revision in the same second")})["entry"]
    assert revision["supersedes"] == original["guid"]
    later = log.save_entry(document, {"moment": MOMENT + timedelta(seconds=1), "fields": fields("Next second")})["entry"]
    assert log.get_current_entries(document) == [later, revision]
    with pytest.raises(ValueError, match="changed"):
        log.save_entry(document, {"moment": MOMENT, "guid": original["guid"], "expected": original, "fields": fields("Stale")})


@pytest.mark.parametrize("tags", ["UPPER", "has_underscore", "dot.tag", "slash/tag"])
def test_tags_are_full_matches_and_invalid_saves_do_not_change_log(tags):
    document = log.make_document()
    before = deepcopy(document)
    with pytest.raises(ValueError, match="Tags"):
        create(document, fields(tags=tags))
    assert document == before


def test_empty_body_and_space_separated_tags():
    document = log.make_document()
    entry = create(document, fields("", tags="foo  bar-baz foo 123 -"))
    assert entry["tags"] == "foo bar-baz 123 -"
    assert log.get_current_entries(log.load_text(log.save_text(document)))[0]["body"] == ""


def receive(commands, predicate):
    deadline = monotonic() + 5
    while monotonic() < deadline:
        assert not machine.fatal.is_set(), "worker failed"
        try:
            command = commands.get(timeout=0.05)
        except Empty:
            continue
        if predicate(command):
            return command
    pytest.fail("timed out waiting for log result")


def send(event):
    machine.machines["CORE"]["inbox"].put(event)


def save(commands, content, entry=None, overwrite=False):
    request_id = str(uuid4())
    send({"type": "CAPTAINS_LOG_SAVE", "request-id": request_id, "fields": content,
          "guid": entry["guid"] if entry else None, "expected": entry, "overwrite": overwrite})
    return receive(commands, lambda command: command["type"] == "CAPTAINS_LOG_RESULT" and command["request-id"] == request_id)


@pytest.fixture
def project(tmp_path):
    storage.initialize_project(tmp_path)
    commands = main.start_project_workers(tmp_path)
    receive(commands, lambda command: command["type"] == "STATE" and command["ready"])
    yield tmp_path, commands
    if machine.machines["CORE"]["thread"].is_alive() and not machine.fatal.is_set():
        send({"type": "SHUTDOWN"})
        receive(commands, lambda command: command["type"] == "SHUTDOWN_COMPLETE")
    main.finish_worker_shutdown()


def test_optional_log_is_not_created_by_startup_global_save_or_close(project):
    root, commands = project
    send({"type": "SAVE"})
    receive(commands, lambda command: command["type"] == "STATE" and command["status"] == "Project state saved.")
    assert not (root / "db/pydeck26/captainslog.lsf").exists()
    document = workspace.make_default_workspace()
    workspace.apply_layout_event(document, {"type": "CREATE_PROJECT_PANEL", "panel-type": "CAPTAINS_LOG", "position-id": "overview/column-1"})
    workspace.validate_workspace(document)
    assert document["panels"]["project-captains-log"]["label"] == "Captain's Log"


def test_save_results_are_durable_isolated_and_written_only_by_disk(project, monkeypatch):
    root, commands = project
    monkeypatch.setattr(captains_log_core, "current_time", lambda: MOMENT)
    observed = []
    original = storage.save_captains_log

    def observed_save(project_root, document):
        observed.append(current_thread().name)
        original(project_root, document)

    monkeypatch.setattr(storage, "save_captains_log", observed_save)
    first = save(commands, fields("Original"))
    assert first["ok"] and storage.load_captains_log(root)["sections"][1][lsf.KEYS]["guid"] == first["entry"]["guid"]
    second = save(commands, fields("Revision"), first["entry"])
    assert second["ok"] and len(storage.load_captains_log(root)["sections"]) == 3
    third = save(commands, fields("Save Over"), second["entry"], overwrite=True)
    assert third["ok"] and len(storage.load_captains_log(root)["sections"]) == 3
    third["entries"][0]["body"] = "Not shared"
    assert log.get_current_entries(mem.documents["captains-log"])[0]["body"] == "Save Over"
    assert log.get_current_entries(core.documents["captains-log"])[0]["body"] == "Save Over"
    assert observed == ["PyDeck DISK"] * 3


def test_held_disk_save_is_not_acknowledged_early_and_close_waits(project, monkeypatch):
    root, commands = project
    entered, release = Event(), Event()
    original = disk.HANDLERS["WRITE_DOCUMENTS"]

    def held_write():
        entered.set()
        assert release.wait(5)
        original()

    monkeypatch.setitem(disk.HANDLERS, "WRITE_DOCUMENTS", held_write)
    send({"type": "CAPTAINS_LOG_SAVE", "request-id": "held", "fields": fields("Durable note")})
    assert entered.wait(5)
    assert not captains_log_core.entries
    assert not (root / "db/pydeck26/captainslog.lsf").exists()
    send({"type": "SHUTDOWN"})
    queued = []
    while not commands.empty():
        queued.append(commands.get_nowait())
    assert not any(command["type"] in {"CAPTAINS_LOG_RESULT", "SHUTDOWN_COMPLETE"} for command in queued)
    release.set()
    receive(commands, lambda command: command["type"] == "SHUTDOWN_COMPLETE")
    assert log.get_current_entries(storage.load_captains_log(root))[0]["body"] == "Durable note"
