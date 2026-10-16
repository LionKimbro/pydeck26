"""Real Tk coverage for Git hosting, checkbox clicks, drafts, menus, and commits."""

from copy import deepcopy
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic
from types import SimpleNamespace
import tkinter
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydeck26 import framing, git_ui, machine, main, tk, workspace
from pydeck26.storage import initialize_project


def run():
    with TemporaryDirectory() as folder:
        project = Path(folder)
        initialize_project(project)
        for args in (["init", "--initial-branch=main"], ["config", "user.name", "Panel Test"],
                     ["config", "user.email", "panel@example.invalid"], ["config", "commit.gpgsign", "false"],
                     ["config", "core.hooksPath", str(project / "no-hooks")]):
            subprocess.run(["git", *args], cwd=project, check=True, capture_output=True)
        (project / "example.txt").write_text("An example file\n")
        errors, notices, opened = [], [], []
        state = {"step": 0, "target": None, "deadline": monotonic() + 25}
        root = tkinter.Tk()
        root.report_callback_exception = lambda *error: errors.append(error)
        git_ui.messagebox.showinfo = lambda *args, **kwargs: notices.append(args)
        git_ui.messagebox.askyesno = lambda *args, **kwargs: True
        tk.os.startfile = lambda path: opened.append(path)

        def drive():
            try:
                assert monotonic() < state["deadline"], state
                assert not errors, errors
                view = tk.g["view"]
                if view and view["ready"]:
                    document = view["documents"]["workspace"]
                    if state["step"] == 0:
                        framing.request({"type": "CREATE_TAB", "label": "Git"})
                        state["step"] = 1
                    elif state["step"] == 1 and document["selected-tab-id"] != "cockpit":
                        tab = workspace.get_tab(document, document["selected-tab-id"])
                        row = tab["row-ids"][0]
                        target = workspace.position_id(row, 1)
                        state["target"] = target
                        framing.request({"type": "SET_ROW_HEIGHT", "row-id": row, "height": 460})
                        selector = framing.slots[target]["selector"]
                        selector.current(list(selector["values"]).index("[+ Git]"))
                        selector.event_generate("<<ComboboxSelected>>")
                        state["step"] = 2
                    elif state["step"] == 2 and git_ui.panels and not git_ui.g["state"]["busy"] and git_ui.g["state"]["snapshot"]:
                        panel = git_ui.panels["project-git"]
                        listing = panel["lists"]["unstaged"]
                        assert any(item["path"] == "example.txt" for item in listing["records"].values())
                        iid = next(iid for iid, item in listing["records"].items() if item["path"] == "example.txt")
                        tree = listing["tree"]
                        assert tree.heading("size", "text") == "File size"
                        assert tree.heading("diff", "text") == "Diff (+/− lines)"
                        assert tree.set(iid, "size").endswith(" B")
                        assert tree.set(iid, "diff") == "+1 −0"
                        x, y, width, height = tree.bbox(iid, "path")
                        tree.event_generate("<Button-1>", x=x+10, y=y+height//2)
                        assert listing["checked"] == {"example.txt"}
                        assert tree.item(iid, "text") == "☑"
                        git_ui.g["message-var"].set("A draft that survives refresh")
                        panel["refresh"].invoke()
                        state["step"] = 3
                    elif state["step"] == 3 and not git_ui.g["state"]["busy"] and git_ui.g["state"].get("operation") == "refresh":
                        panel = git_ui.panels["project-git"]
                        assert git_ui.g["message-var"].get() == "A draft that survives refresh"
                        listing = panel["lists"]["unstaged"]
                        iid = next(iid for iid, item in listing["records"].items() if item["path"] == "example.txt")
                        tree = listing["tree"]
                        x, y, width, height = tree.bbox(iid, "path")
                        listing["menu"].tk_popup = lambda *args: None
                        git_ui.handle_when_file_menu_requested(SimpleNamespace(y=y+height//2, x_root=10, y_root=10), (panel, "unstaged"))
                        menu = listing["menu"]
                        assert [menu.entrycget(index, "label") for index in range(3)] == ["View File", "View Diff", "Open File"]
                        assert listing["checked"] == {"example.txt"}
                        menu.unpost()
                        menu.invoke(0)
                        state["step"] = 4
                    elif state["step"] == 4 and git_ui.g["state"].get("viewer"):
                        assert "An example file" in git_ui.g["state"]["viewer"]["text"]
                        panel = git_ui.panels["project-git"]
                        panel["buttons"]["stage"].invoke()
                        state["step"] = 5
                    elif state["step"] == 5 and not git_ui.g["state"]["busy"] and git_ui.g["state"]["snapshot"]["staged"]:
                        panel = git_ui.panels["project-git"]
                        assert not panel["lists"]["staged"]["checked"]
                        assert "disabled" not in panel["buttons"]["commit"].state()
                        panel["buttons"]["commit"].invoke()
                        state["step"] = 6
                    elif state["step"] == 6 and git_ui.g["state"].get("operation") == "commit" and not git_ui.g["state"]["busy"]:
                        assert git_ui.g["state"]["ok"], git_ui.g["state"]
                        assert git_ui.g["message-var"].get() == ""
                        panel = git_ui.panels["project-git"]
                        actual = deepcopy(git_ui.g["state"])
                        for ahead, behind, enabled in ((0, 0, False), (1, 0, True), (0, 1, False), (1, 1, False)):
                            sample = deepcopy(actual)
                            sample["snapshot"].update({"upstream": "origin/main", "ahead": ahead, "behind": behind})
                            git_ui.project_git_state(sample)
                            assert ("disabled" not in panel["push"].state()) == enabled
                        git_ui.project_git_state(actual)
                        def finish():
                            if len(sys.argv) > 1:
                                capture_window(tk.widgets["window"], Path(sys.argv[1]))
                            tk.handle_when_user_closes_main_cockpit()
                        root.after(300, finish)
                        state["step"] = 7
                if state["step"] != 7:
                    root.after(25, drive)
            except BaseException:
                errors.append(sys.exc_info())
                root.destroy()

        root.after(25, drive)
        main.run_project(project, root=root)
        if errors:
            for error in errors:
                traceback.print_exception(*error)
            raise AssertionError("Git GUI regression failed")
        assert state["step"] == 7
        assert not notices
        assert all(not runtime["thread"].is_alive() for runtime in machine.get_machine_runtimes())


def capture_window(window, destination):
    import ctypes
    from ctypes import wintypes
    from PIL import ImageGrab

    window.update_idletasks()
    get_ancestor = ctypes.windll.user32.GetAncestor
    get_ancestor.argtypes = [wintypes.HWND, wintypes.UINT]
    get_ancestor.restype = wintypes.HWND
    ImageGrab.grab(window=get_ancestor(window.winfo_id(), 2)).save(destination)


if __name__ == "__main__":
    run()
