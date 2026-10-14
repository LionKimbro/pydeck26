"""Real-Tk workspace controls and restart, using only a temporary project."""

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import monotonic
import tkinter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydeck26 import framing, machine, main, tk, workspace
from pydeck26.storage import initialize_project, load_whiteboard


def run():
    with TemporaryDirectory() as folder:
        project = Path(folder)
        initialize_project(project)
        errors = []
        state = {"stage": 0, "tab-id": None, "row-id": None, "notes": []}
        root = tkinter.Tk()
        root.report_callback_exception = lambda *error: errors.append(error)
        deadline = monotonic() + 10

        def click_row_button(label):
            frame = framing.rows[state["row-id"]]["frame"]
            rail = next(child for child in frame.winfo_children() if child.winfo_class() == "TFrame")
            button = next(child for child in rail.winfo_children() if child.cget("text") == label)
            button.invoke()

        def drive():
            try:
                assert monotonic() < deadline, f"workspace timeout at {state['stage']}"
                assert not errors, errors
                view = tk.g["view"]
                if not view or not view["ready"]:
                    root.after(10, drive)
                    return
                document = view["documents"]["workspace"]
                if state["stage"] == 0:
                    tk.widgets["whiteboard-editor"].insert("end", "project draft before switching tabs")
                    framing.simpledialog.askstring = lambda *args, **kwargs: "Workbench"
                    framing.handle_when_user_creates_tab()
                    state["stage"] = 1
                elif state["stage"] == 1 and document["selected-tab-id"] != "cockpit":
                    assert "whiteboard-editor" not in tk.widgets
                    assert view["documents"]["whiteboard"] == "project draft before switching tabs"
                    state["tab-id"] = document["selected-tab-id"]
                    state["row-id"] = workspace.get_tab(document, state["tab-id"])["row-ids"][0]
                    click_row_button("x3")
                    state["stage"] = 2
                elif state["stage"] == 2 and document["rows"][state["row-id"]]["column-count"] == 3:
                    slot = framing.slots[workspace.position_id(state["row-id"], 1)]
                    slot["selector"].current(slot["available-panel-ids"].index("project-whiteboard"))
                    slot["selector"].event_generate("<<ComboboxSelected>>")
                    for column in (2, 3):
                        slot = framing.slots[workspace.position_id(state["row-id"], column)]
                        choices = list(slot["selector"]["values"])
                        slot["selector"].current(choices.index("[+ Notes]"))
                        slot["selector"].event_generate("<<ComboboxSelected>>")
                    state["stage"] = 3
                elif state["stage"] == 3 and len(tk.notes_editors) == 2 and "whiteboard-editor" in tk.widgets:
                    assert tk.widgets["whiteboard-editor"].get("1.0", "end-1c") == "project draft before switching tabs"
                    state["notes"] = list(tk.notes_editors)
                    for index, panel_id in enumerate(state["notes"]):
                        tk.notes_editors[panel_id].insert("end", f"independent note {index}")
                    # A geometry transition flushes both text drafts before persisting.
                    live = framing.rows[state["row-id"]]
                    pane = live["pane"]
                    root.update_idletasks()
                    width = pane.winfo_width()
                    pane.sashpos(0, round(width * 0.25))
                    pane.sashpos(1, round(width * 0.7))
                    pane.event_generate("<ButtonRelease-1>")
                    handle = live["resize-handle"]
                    handle.event_generate("<ButtonPress-1>", rooty=400)
                    handle.event_generate("<B1-Motion>", rooty=520)
                    root.update_idletasks()
                    handle.event_generate("<ButtonRelease-1>", rooty=520)
                    framing.handle_when_user_adds_row()
                    state["stage"] = 4
                elif state["stage"] == 4 and len(workspace.get_tab(document, state["tab-id"])["row-ids"]) == 2:
                    for index, panel_id in enumerate(state["notes"]):
                        assert document["panels"][panel_id]["text"] == f"independent note {index}"
                    assert document["rows"][state["row-id"]]["height"] >= 360
                    framing.handle_when_scrollbar_moves_tab(state["tab-id"], ("moveto", 0.2))
                    # Use the actual notebook selection callback, flushing outgoing drafts.
                    framing.widgets["notebook"].select(framing.pages["cockpit"]["page"])
                    state["stage"] = 5
                elif state["stage"] == 5 and document["selected-tab-id"] == "cockpit":
                    assert tk.widgets["whiteboard-editor"].get("1.0", "end-1c") == "project draft before switching tabs"
                    framing.widgets["notebook"].select(framing.pages[state["tab-id"]]["page"])
                    state["stage"] = 6
                elif state["stage"] == 6 and document["selected-tab-id"] == state["tab-id"]:
                    tk.notes_editors[state["notes"][0]].insert("end", " pending close")
                    tk.handle_when_user_closes_main_cockpit()
                    state["stage"] = 7
                    return
                root.after(10, drive)
            except BaseException as error:
                errors.append(error)
                root.destroy()

        root.after(10, drive)
        main.run_project(project, root=root)
        assert not errors, errors
        assert state["stage"] == 7
        stored = json.loads((project / "db/pydeck26/workspace.json").read_text())
        assert stored["panels"][state["notes"][0]]["text"] == "independent note 0 pending close"
        assert load_whiteboard(project) == "project draft before switching tabs"
        assert stored["selected-tab-id"] == state["tab-id"]
        assert all(not runtime["thread"].is_alive() for runtime in machine.machines.values())

        # Restart reconstructs widgets and restores canonical geometry.
        root = tkinter.Tk()
        root.report_callback_exception = lambda *error: errors.append(error)
        deadline = monotonic() + 8

        def verify_restart():
            try:
                assert monotonic() < deadline
                if not tk.g["view"] or not tk.g["view"]["ready"]:
                    root.after(10, verify_restart)
                    return
                assert tk.g["view"]["documents"]["workspace"] == stored
                root.update_idletasks()
                live = framing.rows[state["row-id"]]
                assert live["frame"].winfo_height() == stored["rows"][state["row-id"]]["height"]
                width = live["pane"].winfo_width()
                assert width > 1
                for index, fraction in enumerate(stored["rows"][state["row-id"]]["sash-proportions"]):
                    assert abs(live["pane"].sashpos(index) / width - fraction) < 0.02
                for panel_id in state["notes"]:
                    assert tk.notes_editors[panel_id].get("1.0", "end-1c") == stored["panels"][panel_id]["text"]
                canvas = framing.pages[state["tab-id"]]["canvas"]
                expected_scroll = workspace.get_tab(stored, state["tab-id"])["scroll-position"]
                assert abs(canvas.yview()[0] - expected_scroll) < 0.04
                tk.handle_when_user_closes_main_cockpit()
            except BaseException as error:
                errors.append(error)
                root.destroy()

        root.after(60, verify_restart)
        main.run_project(project, root=root)
        assert not errors, errors
        print("GUI workspace roundtrip passed")


if __name__ == "__main__":
    run()
