"""Real-Tk image import, drawing, resizing, restart, clearing, and drop reception."""

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import monotonic
from types import SimpleNamespace
import tkinter
import traceback

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydeck26 import framing, image_ui, machine, main, tk, workspace
from pydeck26.storage import initialize_project


def run():
    with TemporaryDirectory() as folder:
        project = Path(folder)
        initialize_project(project)
        source = project / "source image with spaces.png"
        Image.new("RGB", (640, 320), "#b0c0d0").save(source)
        original = source.read_bytes()
        errors = []
        state = {"step": 0, "panel-id": None, "row-id": None, "asset": None, "photo-height": None}
        root = tkinter.Tk()
        root.report_callback_exception = lambda *error: errors.append(error)
        deadline = monotonic() + 12

        def draw(panel, finish=True):
            canvas = panel["canvas"]
            x, y = canvas.winfo_width() // 2, canvas.winfo_height() // 2
            canvas.event_generate("<ButtonPress-1>", x=x-20, y=y-10)
            canvas.event_generate("<B1-Motion>", x=x+20, y=y+10)
            if finish:
                canvas.event_generate("<ButtonRelease-1>", x=x+30, y=y+10)

        def drive():
            try:
                assert monotonic() < deadline, state
                assert not errors, errors
                view = tk.g["view"]
                if not view or not view["ready"]:
                    root.after(20, drive)
                    return
                document = view["documents"]["workspace"]
                if state["step"] == 0:
                    framing.request({"type": "CREATE_TAB", "label": "Images"})
                    state["step"] = 1
                elif state["step"] == 1 and document["selected-tab-id"] != "cockpit":
                    tab = workspace.get_tab(document, document["selected-tab-id"])
                    state["row-id"] = tab["row-ids"][0]
                    target = workspace.position_id(state["row-id"], 1)
                    selector = framing.slots[target]["selector"]
                    selector.current(list(selector["values"]).index("[+ Image]"))
                    selector.event_generate("<<ComboboxSelected>>")
                    state["step"] = 2
                elif state["step"] == 2 and image_ui.panels:
                    state["panel-id"] = next(iter(image_ui.panels))
                    panel = image_ui.panels[state["panel-id"]]
                    assert "selector" not in framing.slots[workspace.position_id(state["row-id"], 1)]
                    image_ui.filedialog.askopenfilename = lambda **kwargs: str(source)
                    panel["browse"].invoke()
                    state["step"] = 3
                elif state["step"] == 3 and image_ui.panels[state["panel-id"]]["photo"]:
                    panel = image_ui.panels[state["panel-id"]]
                    state["asset"] = document["panels"][state["panel-id"]]["image-asset"]
                    assert (project / "db/pydeck26" / state["asset"]).read_bytes() == original
                    assert panel["photo"].width() <= panel["canvas"].winfo_width()
                    assert panel["photo"].height() <= panel["canvas"].winfo_height()
                    state["photo-height"] = panel["photo"].height()
                    panel["pen"].invoke()
                    draw(panel)
                    assert panel["save-id"] is not None
                    framing.request({"type": "SET_ROW_HEIGHT", "row-id": state["row-id"], "height": 420})
                    state["step"] = 4
                elif state["step"] == 4:
                    panel = image_ui.panels[state["panel-id"]]
                    strokes = document["panels"][state["panel-id"]]["image-strokes"]
                    if len(strokes) == 1 and panel["photo"] and panel["photo"].height() > state["photo-height"]:
                        assert len(panel["canvas"].find_withtag("image-ink")) == 1
                        draw(panel, finish=False)
                        assert panel["stroke"] is not None
                        tk.handle_when_user_closes_main_cockpit()
                        state["step"] = 5
                        return
                root.after(20, drive)
            except BaseException as error:
                traceback.print_exc()
                errors.append(error)
                root.destroy()

        root.after(20, drive)
        main.run_project(project, root=root)
        assert not errors, errors
        assert state["step"] == 5
        assert source.read_bytes() == original
        asset_path = project / "db/pydeck26" / state["asset"]
        assert asset_path.read_bytes() == original
        saved = json.loads((project / "db/pydeck26/workspace.json").read_text())
        assert len(saved["panels"][state["panel-id"]]["image-strokes"]) == 2
        root = tkinter.Tk()
        root.report_callback_exception = lambda *error: errors.append(error)
        deadline = monotonic() + 10

        def verify_restart():
            try:
                assert monotonic() < deadline, state
                assert not errors, errors
                panel = image_ui.panels.get(state["panel-id"])
                if panel and panel["photo"] and state["step"] == 5:
                    assert len(panel["canvas"].find_withtag("image-ink")) == 2
                    panel["clear"].invoke()
                    state["step"] = 6
                elif panel and state["step"] == 6 and not panel["asset"]:
                    assert not panel["photo"]
                    assert panel["strokes"] == []
                    root.update_idletasks()
                    assert panel["paste"].winfo_ismapped()
                    assert asset_path.read_bytes() == original
                    # Tcl list decoding preserves the spaces in dropped file paths.
                    assert image_ui.handle_when_user_drops_image(SimpleNamespace(data="{" + str(source) + "}"), panel) == "copy"
                    state["step"] = 7
                elif panel and state["step"] == 7 and panel["photo"]:
                    assert panel["strokes"] == []
                    panel["clear"].invoke()
                    state["step"] = 8
                elif panel and state["step"] == 8 and not panel["asset"]:
                    tk.handle_when_user_closes_main_cockpit()
                    return
                root.after(20, verify_restart)
            except BaseException as error:
                traceback.print_exc()
                errors.append(error)
                root.destroy()

        root.after(20, verify_restart)
        main.run_project(project, root=root)
        assert not errors, errors
        assert state["step"] == 8
        saved = json.loads((project / "db/pydeck26/workspace.json").read_text())
        assert saved["panels"][state["panel-id"]]["image-asset"] is None
        assert all(not runtime["thread"].is_alive() for runtime in machine.machines.values())
        assert asset_path.read_bytes() == original
        print("GUI image roundtrip passed")


if __name__ == "__main__":
    run()
