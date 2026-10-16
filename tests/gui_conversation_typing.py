"""Deterministic real-Tk typing regression with Core held behind queued updates."""

from copy import deepcopy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic
import tkinter
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydeck26 import core, main, tk
from pydeck26.storage import initialize_project, save_conversations


def run():
    # Optional comparison runs the same behavioral reproduction against the old handlers.
    if "--baseline" in sys.argv:
        import ast
        import subprocess
        baseline = "8e8227b57ae73f5a1a784648a8afb9c0a34a6951"
        source = subprocess.run(["git", "show", f"{baseline}:src/pydeck26/tk.py"],
                                capture_output=True, text=True, check=True).stdout
        names = {"project_conversation_rows", "handle_when_conversation_editor_changes", "build_conversation_entry"}
        definitions = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name in names]
        exec(compile(ast.Module(body=definitions, type_ignores=[]), "previous_tk.py", "exec"), tk.__dict__)

    with TemporaryDirectory() as folder:
        project = Path(folder)
        initialize_project(project)
        first = {"id": "first", "date": "2026-10-15", "title": "First conversation",
                 "url": "https://example.invalid/first", "hook": "First hook", "description": "First description"}
        others = [{**first, "id": f"other-{index}", "date": f"2026-09-{index + 1:02d}",
                   "title": f"Other {index}"} for index in range(28)]
        save_conversations(project, {"items": [first, *others]})
        started, release = Event(), Event()
        original_reduce = core.reduce_event

        def held_reduce(event):
            if event.get("text") == "typing-regression-barrier":
                started.set()
                assert release.wait(5)
            original_reduce(event)

        core.reduce_event = held_reduce
        errors = []
        root = tkinter.Tk()
        root.report_callback_exception = lambda *error: errors.append(error)
        stage = {"value": 0, "column": 0, "stale": None, "expected": None, "cursor": None, "scroll": None}
        fields = ("date", "title", "url", "hook")
        deadline = monotonic() + 10

        def drive():
            try:
                assert monotonic() < deadline, stage
                assert not errors, errors
                view = tk.g["view"]
                if not view or not view["ready"]:
                    root.after(10, drive)
                    return
                if stage["value"] == 0:
                    assert tk.g["conversation-id"] == "first"
                    tree = tk.widgets["conversation-tree"]
                    root.update_idletasks()
                    tree.yview_moveto(0.5)
                    stage["scroll"] = tree.yview()
                    tk.send({"type": "STATUS", "text": "typing-regression-barrier"})
                    stage["value"] = 1
                elif stage["value"] == 1 and started.is_set():
                    column = fields[stage["column"]]
                    entry = tk.widgets[f"conversation-{column}"]
                    stale = deepcopy(view)
                    stale["seq"] = tk.g["seq"]
                    stage["stale"] = stale
                    # This is Tk's Entry edit step, before any KeyRelease handler can run.
                    entry.icursor(2)
                    entry.insert("insert", "X")
                    entry.selection_range(1, 3)
                    stage["expected"] = entry.get()
                    stage["cursor"] = (entry.index("insert"), entry.index("sel.first"), entry.index("sel.last"))
                    tk.g["commands"].put(stale)
                    stage["value"] = 2
                    root.after(50, drive)
                    return
                elif stage["value"] == 2:
                    column = fields[stage["column"]]
                    entry = tk.widgets[f"conversation-{column}"]
                    assert entry.get() == stage["expected"], f"{column}: incoming projection replaced a new edit before KeyRelease"
                    assert (entry.index("insert"), entry.index("sel.first"), entry.index("sel.last")) == stage["cursor"]
                    # Even an accepted same-record refresh must leave the editor draft alone.
                    tk.project_core_state(stage["stale"])
                    assert entry.get() == stage["expected"], f"{column}: routine refresh echoed older text into the draft"
                    assert (entry.index("insert"), entry.index("sel.first"), entry.index("sel.last")) == stage["cursor"]
                    assert tk.widgets["conversation-tree"].yview() == stage["scroll"]
                    entry.selection_clear()
                    # Returning to the old value before Core catches up must submit that edit too.
                    entry.delete(2, 3)
                    assert entry.get() == first[column]
                    if column == "title":
                        # StringVar changes exercise the path used by paste/IME, without reading the clipboard.
                        tk.widgets["conversation-title-variable"].set("Final title from paste")
                    stage["column"] += 1
                    if stage["column"] < len(fields):
                        stage["value"] = 1
                    else:
                        release.set()
                        stage["value"] = 3
                elif stage["value"] == 3 and view["seq"] == tk.g["seq"]:
                    current = next(item for item in view["documents"]["conversations"]["items"] if item["id"] == "first")
                    assert current["title"] == "Final title from paste"
                    for column in ("date", "url", "hook"):
                        assert current[column] == first[column], f"{column}: reverting an unacknowledged edit was lost"
                    # Load another conversation, then restore the first; draft protection must not block navigation.
                    tree = tk.widgets["conversation-tree"]
                    tree.selection_set("other-0")
                    tk.handle_when_user_selects_conversation()
                    stage["value"] = 4
                elif stage["value"] == 4 and tk.g["conversation-id"] == "other-0":
                    assert tk.widgets["conversation-title"].get() == "Other 0"
                    tree = tk.widgets["conversation-tree"]
                    tree.selection_set("first")
                    tk.handle_when_user_selects_conversation()
                    stage["value"] = 5
                elif stage["value"] == 5 and tk.g["conversation-id"] == "first":
                    assert tk.widgets["conversation-title"].get() == "Final title from paste"
                    tk.handle_when_user_closes_main_cockpit()
                    stage["value"] = 6
                    return
                root.after(10, drive)
            except BaseException as error:
                traceback.print_exc()
                errors.append(error)
                release.set()
                root.destroy()

        root.after(10, drive)
        main.run_project(project, root=root)
        assert not errors, errors
        assert stage["value"] == 6
        saved = json.loads((project / "db/pydeck26/conversations.json").read_text())
        assert next(item for item in saved["items"] if item["id"] == "first")["title"] == "Final title from paste"
        print("Conversation typing regression passed")


if __name__ == "__main__":
    run()
