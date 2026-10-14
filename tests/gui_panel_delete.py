"""Exercise dropdown creation, unhosting, Ctrl-click deletion and explicit recreation."""

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import monotonic
import tkinter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydeck26 import framing, main, tk, workspace
from pydeck26.storage import initialize_project, load_whiteboard, save_whiteboard


def run():
    with TemporaryDirectory() as folder:
        project = Path(folder)
        initialize_project(project)
        save_whiteboard(project, "project file stays here")
        errors, sent = [], []
        state = {"stage": -1, "panel-id": None, "target": None}
        root = tkinter.Tk()
        root.report_callback_exception = lambda *error: errors.append(error)
        deadline = monotonic() + 8

        def choose(target, label):
            selector = framing.slots[target]["selector"]
            selector.current(list(selector["values"]).index(label))
            selector.event_generate("<<ComboboxSelected>>")

        def control_delete(target):
            button = framing.slots[target]["unhost-button"]
            sent.clear()
            button.event_generate("<ButtonPress-1>", state=4)
            button.event_generate("<ButtonRelease-1>", state=4)
            assert sent == ["DELETE_PANEL"], sent

        def drive():
            try:
                assert monotonic() < deadline, state
                assert not errors, errors
                view = tk.g["view"]
                if not view or not view["ready"]:
                    root.after(10, drive)
                    return
                document = view["documents"]["workspace"]
                if state["stage"] == -1:
                    def observed_send(event):
                        sent.append(event["type"])
                        tk.send(event)
                    framing.g["send"] = observed_send
                    assert "selector" not in framing.slots["overview/column-1"]
                    framing.slots["overview/column-1"]["unhost-button"].invoke()
                    state["stage"] = 0
                elif state["stage"] == 0 and document["positions"]["overview/column-1"]["panel-id"] is None:
                    choose("overview/column-1", "[+ Notes]")
                    state["stage"] = 1
                elif state["stage"] == 1 and tk.notes_editors:
                    state["panel-id"] = next(iter(tk.notes_editors))
                    tk.notes_editors[state["panel-id"]].insert("end", "permanent deletion test")
                    framing.request({"type": "CREATE_TAB", "label": "Shared"})
                    state["stage"] = 2
                elif state["stage"] == 2 and document["selected-tab-id"] != "cockpit":
                    tab = workspace.get_tab(document, document["selected-tab-id"])
                    target = workspace.position_id(tab["row-ids"][0], 1)
                    state["target"] = target
                    slot = framing.slots[target]
                    slot["selector"].current(slot["available-panel-ids"].index(state["panel-id"]))
                    slot["selector"].event_generate("<<ComboboxSelected>>")
                    state["stage"] = 3
                elif state["stage"] == 3 and state["panel-id"] in tk.notes_editors:
                    assert tk.notes_editors[state["panel-id"]].get("1.0", "end-1c") == "permanent deletion test"
                    framing.slots[state["target"]]["unhost-button"].invoke()
                    state["stage"] = 4
                elif state["stage"] == 4 and not tk.notes_editors:
                    assert state["panel-id"] in document["panels"]
                    slot = framing.slots[state["target"]]
                    slot["selector"].current(slot["available-panel-ids"].index(state["panel-id"]))
                    slot["selector"].event_generate("<<ComboboxSelected>>")
                    state["stage"] = 5
                elif state["stage"] == 5 and tk.notes_editors:
                    control_delete(state["target"])
                    state["stage"] = 6
                elif state["stage"] == 6 and state["panel-id"] not in document["panels"]:
                    assert document["positions"]["overview/column-1"]["panel-id"] is None
                    assert document["positions"][state["target"]]["panel-id"] is None
                    framing.request({"type": "SELECT_TAB", "tab-id": "cockpit"})
                    state["stage"] = 7
                elif state["stage"] == 7 and document["selected-tab-id"] == "cockpit":
                    control_delete("whiteboard/column-1")
                    state["stage"] = 8
                elif state["stage"] == 8 and "project-whiteboard" not in document["panels"]:
                    assert "[+ Whiteboard]" in framing.slots["whiteboard/column-1"]["selector"]["values"]
                    tk.handle_when_user_closes_main_cockpit()
                    state["stage"] = 9
                    return
                root.after(10, drive)
            except BaseException as error:
                errors.append(error)
                root.destroy()

        root.after(10, drive)
        main.run_project(project, root=root)
        assert not errors, errors
        assert state["stage"] == 9
        stored = json.loads((project / "db/pydeck26/workspace.json").read_text())
        assert state["panel-id"] not in stored["panels"]
        assert "project-whiteboard" not in stored["panels"]
        assert load_whiteboard(project) == "project file stays here"
        root = tkinter.Tk()
        root.report_callback_exception = lambda *error: errors.append(error)
        deadline = monotonic() + 8
        state["stage"] = 10

        def recreate_after_restart():
            try:
                assert monotonic() < deadline
                view = tk.g["view"]
                if view and view["ready"]:
                    document = view["documents"]["workspace"]
                    assert state["panel-id"] not in document["panels"]
                    if state["stage"] == 10:
                        assert "project-whiteboard" not in document["panels"]
                        choose("whiteboard/column-1", "[+ Whiteboard]")
                        state["stage"] = 11
                    elif "whiteboard-editor" in tk.widgets:
                        assert tk.widgets["whiteboard-editor"].get("1.0", "end-1c") == "project file stays here"
                        tk.handle_when_user_closes_main_cockpit()
                        return
                root.after(10, recreate_after_restart)
            except BaseException as error:
                errors.append(error)
                root.destroy()

        root.after(10, recreate_after_restart)
        main.run_project(project, root=root)
        assert not errors, errors
        print("GUI panel deletion passed")


if __name__ == "__main__":
    run()
