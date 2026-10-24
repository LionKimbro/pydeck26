"""Exercise request validation, failed save/retry, and duplicate-click prevention."""

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import monotonic
import tkinter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import sweeperagent
from pydeck26 import machine, main, sweeper_ui, tk


def run():
    with TemporaryDirectory() as folder:
        project = Path(folder)
        root = tkinter.Tk()
        errors = []
        root.report_callback_exception = lambda *error: errors.append(error)
        original = sweeperagent.create_request
        attempt = {"count": 0}

        def create_request(project_root, record):
            attempt["count"] += 1
            if attempt["count"] == 1:
                raise PermissionError("Simulated write failure")
            return original(project_root, record)

        sweeperagent.create_request = create_request
        deadline = monotonic() + 12
        state = {"step": 0}

        def drive():
            try:
                assert monotonic() < deadline, state
                assert not errors, errors
                if not tk.g["view"] or not tk.g["view"]["ready"]:
                    root.after(20, drive)
                    return
                if state["step"] == 0:
                    toolbar = tk.widgets["workspace-root"].winfo_children()[0]
                    button = next(child for child in toolbar.winfo_children()
                                  if child.cget("text") == "+ Sweeper request")
                    button.invoke()
                    form = sweeper_ui.widgets
                    form["save"].invoke()
                    assert "title and a description" in form["status"].cget("text")
                    form["title"].insert(0, "Test capture")
                    form["description"].insert("1.0", "Details: café 🌿\nSecond line")
                    form["directive"].set("Please hold")
                    form["save"].invoke()
                    sweeper_ui.handle_when_user_saves_request()
                    assert "disabled" in form["save"].state()
                    state["step"] = 1
                elif state["step"] == 1 and sweeper_ui.g["token"] is None:
                    form = sweeper_ui.widgets
                    assert "Simulated write failure" in form["status"].cget("text")
                    assert form["title"].get() == "Test capture"
                    assert form["description"].get("1.0", "end-1c") == "Details: café 🌿\nSecond line"
                    assert not (project / "db" / "sweep-requests").exists()
                    form["save"].invoke()
                    sweeper_ui.handle_when_user_saves_request()
                    state["step"] = 2
                elif state["step"] == 2 and sweeper_ui.g["dialog"] is None:
                    files = list((project / "db" / "sweep-requests").glob("*.json"))
                    assert len(files) == 1
                    record = json.loads(files[0].read_text(encoding="utf-8"))
                    assert record["request"]["directive"] == "please-hold"
                    assert record["request"]["title"] == "Test capture"
                    assert record["project"]["name"] == project.name
                    assert attempt["count"] == 2
                    tk.handle_when_user_creates_sweeper_request()
                    sweeper_ui.widgets["cancel"].invoke()
                    assert sweeper_ui.g["dialog"] is None
                    tk.handle_when_user_closes_main_cockpit()
                    state["step"] = 3
                if state["step"] != 3:
                    root.after(20, drive)
            except BaseException:
                errors.append(sys.exc_info())
                root.destroy()

        root.after(20, drive)
        main.run_project(project, root=root)
        if errors:
            import traceback
            for error in errors:
                traceback.print_exception(*error)
            raise AssertionError("Sweeper GUI regression failed")
        assert state["step"] == 3
        assert all(not runtime["thread"].is_alive() for runtime in machine.get_machine_runtimes())


if __name__ == "__main__":
    run()
