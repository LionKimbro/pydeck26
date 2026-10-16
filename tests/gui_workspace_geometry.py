"""Restore asymmetric rows containing the nested Captain's Log paned window."""

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import monotonic
import tkinter
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydeck26 import captains_log_ui, framing, main, panel_geometry, storage, tk, workspace


def run():
    with TemporaryDirectory() as folder:
        project = Path(folder)
        storage.initialize_project(project)
        document = workspace.make_default_workspace()
        workspace.apply_layout_event(document, {"type": "CREATE_TAB", "label": "History"})
        tab_id = document["selected-tab-id"]
        row_id = workspace.get_tab(document, tab_id)["row-ids"][0]
        workspace.apply_layout_event(document, {"type": "SET_ROW_COLUMNS", "row-id": row_id, "column-count": 2})
        workspace.apply_layout_event(document, {"type": "HOST_PANEL", "position-id": workspace.position_id(row_id, 1), "panel-id": "project-dictionary"})
        workspace.apply_layout_event(document, {"type": "CREATE_PROJECT_PANEL", "position-id": workspace.position_id(row_id, 2), "panel-type": "CAPTAINS_LOG"})
        document["rows"][row_id].update({"height": 420, "sash-proportions": [0.18]})
        workspace.apply_layout_event(document, {"type": "ADD_ROW", "tab-id": tab_id})
        triple_row = workspace.get_tab(document, tab_id)["row-ids"][-1]
        workspace.apply_layout_event(document, {"type": "SET_ROW_COLUMNS", "row-id": triple_row, "column-count": 3})
        for column in range(1, 4):
            workspace.apply_layout_event(document, {"type": "CREATE_NOTES", "position-id": workspace.position_id(triple_row, column)})
        workspace.apply_layout_event(document, {"type": "HOST_PANEL", "position-id": workspace.position_id(triple_row, 1), "panel-id": "project-conversations"})
        internal = {"project-captains-log": 0.23, "project-conversations": 0.64}
        for panel_id, proportion in internal.items():
            document["panels"][panel_id]["split-proportion"] = proportion
        document["rows"][triple_row].update({"height": 240, "sash-proportions": [0.70, 0.88]})
        storage.save_workspace(project, document)
        errors = []
        state = {"step": 0, "trips": 0, "expected": [0.18], "deadline": monotonic() + 12}
        root = tkinter.Tk()
        root.report_callback_exception = lambda *error: (errors.append(error), traceback.print_exception(*error))

        def verify_rows():
            root.update_idletasks()
            for identity, expected in ((row_id, state["expected"]), (triple_row, [0.70, 0.88])):
                live = framing.rows[identity]
                pane = live["pane"]
                width = pane.winfo_width()
                actual = [pane.sashpos(index) / width for index in range(len(expected))]
                stored = framing.g["document"]["rows"][identity]["sash-proportions"]
                assert all(abs(a - b) < 0.015 for a, b in zip(actual, expected)), (identity, actual, expected, stored, width, live["last-width"])
                assert live["frame"].winfo_height() == document["rows"][identity]["height"]
            for panel_id, proportion in internal.items():
                pane = panel_geometry.splits[panel_id]["pane"]
                assert pane.winfo_width() > 1
                assert abs(pane.sashpos(0) / pane.winfo_width() - proportion) < 0.015, (panel_id, pane.sashpos(0), pane.winfo_width(), proportion)

        def drive():
            try:
                assert not errors, errors
                assert monotonic() < state["deadline"], state
                view = tk.g["view"]
                if not view or not view["ready"]:
                    root.after(20, drive)
                    return
                if state.get("settled-generation") != framing.g["generation"]:
                    state["settled-generation"] = framing.g["generation"]
                    root.after(100, drive)
                    return
                selected = view["documents"]["workspace"]["selected-tab-id"]
                if state["step"] == 0:
                    verify_rows()
                    pane = framing.rows[row_id]["pane"]
                    x, y = pane.sashpos(0) + 1, pane.winfo_height() // 2
                    destination = round(pane.winfo_width() * 0.27)
                    pane.event_generate("<ButtonPress-1>", x=x, y=y)
                    pane.event_generate("<B1-Motion>", x=destination, y=y)
                    root.update_idletasks()
                    assert framing.rows[row_id]["dragging"]
                    assert abs(pane.sashpos(0) / pane.winfo_width() - 0.27) < 0.015
                    pane.event_generate("<ButtonRelease-1>", x=destination, y=y)
                    state["expected"] = [pane.sashpos(0) / pane.winfo_width()]
                    assert abs(state["expected"][0] - 0.27) < 0.015, state["expected"]
                    captains_log_ui.widgets["body"].insert("1.0", "Unsaved log draft during divider changes")
                    captains_log_ui.capture_draft()
                    for panel_id, proportion in (("project-captains-log", 0.31), ("project-conversations", 0.57)):
                        split = panel_geometry.splits[panel_id]
                        inner = split["pane"]
                        x, y = inner.sashpos(0) + 1, inner.winfo_height() // 2
                        destination = round(inner.winfo_width() * proportion)
                        inner.event_generate("<ButtonPress-1>", x=x, y=y)
                        inner.event_generate("<B1-Motion>", x=destination, y=y)
                        root.update_idletasks()
                        assert split["dragging"]
                        assert abs(inner.sashpos(0) / inner.winfo_width() - proportion) < 0.015
                        inner.event_generate("<ButtonRelease-1>", x=destination, y=y)
                        internal[panel_id] = inner.sashpos(0) / inner.winfo_width()
                    state["step"] = 1
                elif state["step"] == 1:
                    verify_rows()
                    framing.widgets["notebook"].select(framing.pages["cockpit"]["page"])
                    state["step"] = 2
                elif state["step"] == 2 and selected == "cockpit":
                    framing.widgets["notebook"].select(framing.pages[tab_id]["page"])
                    state["step"] = 3
                elif state["step"] == 3 and selected == tab_id:
                    verify_rows()
                    assert captains_log_ui.widgets["body"].get("1.0", "end-1c") == "Unsaved log draft during divider changes"
                    state["trips"] += 1
                    if state["trips"] < 3:
                        state["step"] = 1
                    else:
                        tk.widgets["window"].geometry("1390x850")
                        state["step"] = 4
                elif state["step"] == 4:
                    verify_rows()
                    tk.widgets["window"].geometry("900x650")
                    state["step"] = 5
                elif state["step"] == 5:
                    verify_rows()
                    tk.handle_when_user_closes_main_cockpit()
                    state["step"] = 6
                    return
                root.after(100, drive)
            except BaseException:
                errors.append(sys.exc_info())
                root.destroy()

        root.after(150, drive)
        main.run_project(project, root=root)
        if errors:
            for error in errors:
                traceback.print_exception(*error)
            raise AssertionError("Workspace geometry regression failed")
        assert state["step"] == 6
        stored = json.loads((project / "db/pydeck26/workspace.json").read_text())
        assert stored["rows"][row_id]["sash-proportions"] == state["expected"]
        for panel_id, proportion in internal.items():
            assert stored["panels"][panel_id]["split-proportion"] == proportion
        assert not (project / "db/pydeck26/captainslog.lsf").exists()
        root = tkinter.Tk()
        root.report_callback_exception = lambda *error: (errors.append(error), traceback.print_exception(*error))
        deadline = monotonic() + 5

        def verify_restart():
            try:
                assert monotonic() < deadline
                if not tk.g["view"] or not tk.g["view"]["ready"]:
                    root.after(100, verify_restart)
                    return
                verify_rows()
                tk.handle_when_user_closes_main_cockpit()
            except BaseException:
                errors.append(sys.exc_info())
                root.destroy()

        root.after(200, verify_restart)
        main.run_project(project, root=root)
        if errors:
            for error in errors:
                traceback.print_exception(*error)
            raise AssertionError("Workspace geometry restart regression failed")


if __name__ == "__main__":
    run()
