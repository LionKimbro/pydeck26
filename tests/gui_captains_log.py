"""Real Tk: log drafts, delayed Save, revision/overwrite, minute tick, exit/restart."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic
from types import SimpleNamespace
import tkinter
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydeck26 import captains_log, captains_log_core, captains_log_ui as ui, framing, main, storage, tk, workspace


def select(key):
    ui.widgets["tree"].selection_set(key)
    ui.widgets["tree"].event_generate("<<TreeviewSelect>>")


def run():
    with TemporaryDirectory() as folder:
        project = Path(folder)
        storage.initialize_project(project)
        errors = []
        entered, release = Event(), Event()
        state = {"step": 0, "deadline": monotonic() + 15, "guid": None,
                 "moment": datetime(2026, 10, 15, 19, 42, 8, tzinfo=timezone.utc), "hold": True}
        captains_log_core.current_time = lambda: state["moment"]
        original_writer = storage.save_captains_log

        def held_writer(root, document):
            if state["hold"]:
                entered.set()
                assert release.wait(5)
            original_writer(root, document)

        storage.save_captains_log = held_writer
        root = tkinter.Tk()
        root.report_callback_exception = lambda *error: (errors.append(error), traceback.print_exception(*error))

        def drive():
            try:
                assert not errors, errors
                assert monotonic() < state["deadline"], state
                view = tk.g["view"]
                if view and view["ready"]:
                    document = view["documents"]["workspace"]
                    if state["step"] == 0:
                        framing.request({"type": "CREATE_TAB", "label": "Captain's Log"})
                        state["step"] = 1
                    elif state["step"] == 1 and document["selected-tab-id"] != "cockpit":
                        row = workspace.get_tab(document, document["selected-tab-id"])["row-ids"][0]
                        state["tab"] = document["selected-tab-id"]
                        framing.request({"type": "SET_ROW_HEIGHT", "row-id": row, "height": 470})
                        selector = framing.slots[workspace.position_id(row, 1)]["selector"]
                        selector.current(list(selector["values"]).index("[+ Captain's Log]"))
                        selector.event_generate("<<ComboboxSelected>>")
                        state["step"] = 2
                    elif state["step"] == 2 and ui.widgets and ui.g["initialized"]:
                        assert ui.widgets["tree"].get_children()[0] == "new"
                        assert ui.widgets["tree"].set("new", "hook") == "<new entry>"
                        ui.widgets["body"].insert("1.0", "Original\n\n== Literal note text ==\n")
                        ui.widgets["hook-var"].set("First decision")
                        ui.widgets["tags-var"].set("design captain-log")
                        ui.widgets["major-var"].set(True)
                        ui.capture_draft()
                        assert "dirty" in ui.widgets["tree"].item("new", "tags")
                        ui.widgets["save"].invoke()
                        state["step"] = 3
                    elif state["step"] == 3 and entered.is_set():
                        assert not ui.entries and ui.pending
                        ui.widgets["body"].insert("end", "Newer typing")
                        ui.capture_draft()
                        state["hold"] = False
                        release.set()
                        state["step"] = 4
                    elif state["step"] == 4 and ui.entries and not ui.pending:
                        guid = ui.g["selected"]
                        assert guid != "new" and ui.is_dirty(guid)
                        assert ui.widgets["body"].get("1.0", "end-1c").endswith("Newer typing")
                        saved = captains_log.get_current_entries(storage.load_captains_log(project))[0]
                        assert not saved["body"].endswith("Newer typing")
                        ui.widgets["save"].invoke()
                        state["old-guid"] = guid
                        state["step"] = 5
                    elif state["step"] == 5 and not ui.pending and ui.g["selected"] != state["old-guid"]:
                        guid = ui.g["selected"]
                        state["guid"] = guid
                        assert len(ui.entries) == 1
                        assert ui.entries[guid]["supersedes"] == state["old-guid"]
                        assert "Last edited" in ui.widgets["modified"].cget("text")
                        assert "major" in ui.widgets["tree"].item(guid, "tags")
                        assert len(storage.load_captains_log(project)["sections"]) == 3
                        select("new")
                        ui.widgets["body"].insert("1.0", "Another note")
                        ui.capture_draft()
                        select(guid)
                        assert ui.drafts["new"]["fields"]["body"] == "Another note"
                        ui.widgets["body"].insert("end", " · overwritten")
                        ui.capture_draft()
                        ui.handle_when_control_pressed(SimpleNamespace(keysym="Control_L"))
                        assert ui.widgets["save"].cget("text") == "Save Over"
                        ui.widgets["save"].event_generate("<ButtonPress-1>", state=0x4, x=5, y=5)
                        ui.widgets["save"].event_generate("<ButtonRelease-1>", state=0x4, x=5, y=5)
                        ui.handle_when_control_released(SimpleNamespace(keysym="Control_L"))
                        state["step"] = 6
                    elif state["step"] == 6 and not ui.pending and not ui.is_dirty(state["guid"]):
                        guid = state["guid"]
                        assert ui.g["selected"] == guid and ui.entries[guid]["modified-on"] is None
                        assert ui.widgets["modified"].cget("text") == ""
                        assert len(storage.load_captains_log(project)["sections"]) == 3
                        select("new")
                        ui.widgets["save"].invoke()  # Same-second new note must be ignored.
                        state["step"] = 7
                    elif state["step"] == 7 and not ui.pending:
                        assert ui.g["selected"] == "new" and ui.is_dirty("new")
                        assert len(ui.entries) == 1
                        state["moment"] += timedelta(seconds=1)
                        ui.widgets["save"].invoke()
                        state["step"] = 8
                    elif state["step"] == 8 and not ui.pending and len(ui.entries) == 2:
                        select("new")
                        ui.widgets["body"].insert("1.0", "Discard this new draft on exit")
                        ui.capture_draft()
                        select(state["guid"])
                        ui.widgets["body"].insert("end", " UNSAVED EXISTING EDIT")
                        ui.capture_draft()
                        assert "dirty" in ui.widgets["tree"].item(state["guid"], "tags")
                        assert "dirty" in ui.widgets["tree"].item("new", "tags")
                        # A minute tick, including midnight, is entirely local to Tk.
                        sequence = tk.g["seq"]
                        ui.g["window"].after_cancel(ui.g["clock-id"])
                        ui.datetime = SimpleNamespace(now=lambda: datetime(2026, 10, 16, 0, 0, 0))
                        ui.handle_when_minute_changes()
                        assert ui.widgets["tree"].set("new", "date") == "2026-10-16"
                        assert ui.widgets["tree"].set("new", "time") == "00:00"
                        assert tk.g["seq"] == sequence
                        framing.request({"type": "SELECT_TAB", "tab-id": "cockpit"})
                        state["step"] = 9
                    elif state["step"] == 9 and document["selected-tab-id"] == "cockpit":
                        assert not ui.widgets
                        framing.request({"type": "SELECT_TAB", "tab-id": state["tab"]})
                        state["step"] = 10
                    elif state["step"] == 10 and ui.widgets:
                        assert ui.widgets["body"].get("1.0", "end-1c").endswith("UNSAVED EXISTING EDIT")
                        assert ui.drafts["new"]["fields"]["body"] == "Discard this new draft on exit"
                        tk.handle_when_user_closes_main_cockpit()
                        state["step"] = 11
                if state["step"] != 11:
                    root.after(20, drive)
            except BaseException:
                errors.append(sys.exc_info())
                release.set()
                root.destroy()

        root.after(20, drive)
        main.run_project(project, root=root)
        if errors:
            for error in errors:
                traceback.print_exception(*error)
            raise AssertionError("Captain's Log GUI regression failed")
        assert state["step"] == 11
        document = storage.load_captains_log(project)
        assert len(document["sections"]) == 4
        assert all("UNSAVED" not in entry["body"] and "Discard this" not in entry["body"] for entry in captains_log.get_current_entries(document))

        root = tkinter.Tk()
        root.report_callback_exception = lambda *error: (errors.append(error), traceback.print_exception(*error))
        deadline = monotonic() + 5

        def check_restart():
            try:
                assert monotonic() < deadline
                if not ui.widgets or not ui.g["initialized"]:
                    root.after(20, check_restart)
                    return
                assert len(ui.entries) == 2
                assert ui.g["selected"] == "new" and not ui.is_dirty("new")
                assert ui.widgets["body"].get("1.0", "end-1c") == ""
                select(state["guid"])
                assert "UNSAVED" not in ui.widgets["body"].get("1.0", "end-1c")
                if len(sys.argv) > 1:
                    from gui_git_panel import capture_window
                    root.after(250, lambda: capture_window(tk.widgets["window"], Path(sys.argv[1])))
                root.after(350, tk.handle_when_user_closes_main_cockpit)
            except BaseException:
                errors.append(sys.exc_info())
                root.destroy()

        root.after(20, check_restart)
        main.run_project(project, root=root)
        if errors:
            for error in errors:
                traceback.print_exception(*error)
            raise AssertionError("Captain's Log restart regression failed")


if __name__ == "__main__":
    run()
