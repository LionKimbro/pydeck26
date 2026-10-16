"""Fresh-process real-Tk exercise, always against an isolated temporary project."""

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import monotonic
import tkinter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydeck26 import core, disk, framing, full_dictionary_editor, ideas, machine, main, mem, tk
from pydeck26.storage import initialize_project, load_whiteboard, save_dictionary_entry


def run():
    failure = sys.argv[1] if len(sys.argv) > 1 else None
    with TemporaryDirectory() as folder:
        project = Path(folder)
        initialize_project(project)
        save_dictionary_entry(project, {"id": "test", "identity": {"name": "test"}, "custom": ["keep"]})
        root = tkinter.Tk()
        errors = []
        root.report_callback_exception = lambda *error: errors.append(error)
        deadline = monotonic() + 8
        stage = {"value": -1}

        if failure:
            module, entry = {
                "CORE": (core, "PROJECT_RETURNED"),
                "MEM": (mem, "INSTALL_PROJECT"),
                "DISK": (disk, "LOAD_PROJECT"),
                "FINAL_DISK": (disk, "WRITE_DOCUMENTS"),
            }[failure]

            def fail():
                raise RuntimeError("injected GUI worker failure")

            module.HANDLERS[entry] = fail

        def drive():
            try:
                assert monotonic() < deadline, f"GUI timeout at stage {stage['value']}"
                assert not errors, errors
                view = tk.g["view"]
                if failure == "FINAL_DISK" and view and view["ready"]:
                    tk.widgets["whiteboard-editor"].insert("end", "unsaved final write")
                    tk.handle_when_user_closes_main_cockpit()
                    return
                if stage["value"] == -1 and view and view["ready"]:
                    tree = tk.widgets["conversation-tree"]
                    assert tuple(tree["columns"]) == ("date", "title", "hook")
                    pane = tk.widgets["conversation-pane"]
                    assert str(tree.master) in pane.panes()
                    assert len(pane.panes()) == 2
                    assert pane.master.grid_rowconfigure(2)["weight"] == 1
                    scrollbar = next(child for child in tree.master.winfo_children()
                                     if child.winfo_class() == "TScrollbar")
                    assert tree.cget("yscrollcommand")
                    assert scrollbar.cget("command")
                    header = framing.slots["overview/column-1"]["unhost-button"].master
                    button = next(child for child in header.winfo_children()
                                  if child.winfo_class() == "TButton" and child.cget("text") == "Copy")
                    assert all("selector" not in slot for slot in framing.slots.values())
                    for slot in framing.slots.values():
                        close = slot["unhost-button"]
                        title = next(child for child in close.master.winfo_children()
                                     if child.winfo_class() == "Label")
                        root.update_idletasks()
                        assert close.winfo_y() < title.winfo_y() + title.winfo_height()
                        assert close.winfo_x() > title.winfo_x() + title.winfo_width()
                    assert framing.slots["overview/column-1"]["unhost-button"].winfo_x() > button.winfo_x()
                    button.invoke()
                    stage["value"] = 0
                elif stage["value"] == 0 and view and view["status"] == "Structure JSON copied to clipboard.":
                    assert json.loads(tk.widgets["window"].clipboard_get()) == []
                    entry = tk.widgets["dictionary-title"]
                    entry.delete(0, "end")
                    entry.insert(0, "GUI title")
                    tk.handle_when_dictionary_editor_changes()
                    tk.widgets["whiteboard-editor"].insert("end", "GUI whiteboard")
                    # Submit setup before unrelated asynchronous projections arrive.
                    tk.handle_when_whiteboard_text_changes()
                    tk.handle_when_user_creates_conversation()
                    stage["value"] = 1
                elif stage["value"] == 1 and view and view["selected-conversation-id"]:
                    entry = tk.widgets["conversation-title"]
                    entry.insert(0, "GUI conversation")
                    tk.handle_when_conversation_editor_changes()
                    # Independent windows must save their own draft identities.
                    drafts = []
                    for title in ("First idea", "Second idea"):
                        ideas.open_editor(None)
                        window = ideas.widgets["idea-editor"]
                        field = next(child for child in window.winfo_children()
                                     if child.winfo_class() == "TEntry" and str(child.grid_info().get("row")) == "1")
                        field.insert(0, title)
                        button = next(child for child in window.winfo_children()
                                      if child.winfo_class() == "TButton" and child.cget("text") == "Save")
                        drafts.append(button)
                    for button in reversed(drafts):
                        button.invoke()
                    ideas.open_editor(None)
                    ideas.widgets["idea-editor"].destroy()
                    stage["value"] = 2
                elif stage["value"] == 2 and view and len(view["documents"]["ideas"]["items"]) == 2:
                    conversation = view["documents"]["conversations"]["items"][0]
                    assert tk.widgets["conversation-tree"].item(conversation["id"], "values") == (
                        conversation["date"], "GUI conversation", "")
                    tk.handle_when_user_opens_full_dictionary_entry()
                    editor = full_dictionary_editor.widgets["editor"]
                    editor.delete("1.0", "end")
                    editor.insert("1.0", '{"custom":')
                    full_dictionary_editor.handle_when_json_changes(None)
                    assert not tk.flush_editor_drafts()
                    assert json.loads((project / "db/pydeck26/dictionary-entry.json").read_text())["custom"] == ["keep"]
                    editor.delete("1.0", "end")
                    editor.insert("1.0", '{"custom": ["updated"]}')
                    full_dictionary_editor.handle_when_json_changes(None)
                    tk.widgets["whiteboard-editor"].insert("end", " pending close")
                    tk.handle_when_user_closes_main_cockpit()
                    stage["value"] = 3
                root.after(10, drive)
            except BaseException as error:
                errors.append(error)
                root.destroy()

        if not failure or failure == "FINAL_DISK":
            root.after(10, drive)
        else:
            root.after(8000, root.destroy)
        try:
            main.run_project(project, root=root)
        except SystemExit as error:
            assert failure and error.code == 1
        else:
            assert not failure, "worker failure did not cause exit status 1"
        assert not errors, errors
        assert all(not runtime["thread"].is_alive() for runtime in machine.machines.values())
        if not failure:
            assert stage["value"] == 3
            assert load_whiteboard(project) == "GUI whiteboard pending close"
            dictionary = json.loads((project / "db/pydeck26/dictionary-entry.json").read_text())
            assert dictionary["identity"]["title"] == "GUI title"
            assert dictionary["custom"] == ["updated"]
            conversations = json.loads((project / "db/pydeck26/conversations.json").read_text())
            assert conversations["items"][0]["title"] == "GUI conversation"
            saved_ideas = json.loads((project / "db/ideas.json").read_text())
            assert {item["title"] for item in saved_ideas["items"]} == {"First idea", "Second idea"}
        print("GUI lifecycle passed", failure or "normal")


if __name__ == "__main__":
    run()
