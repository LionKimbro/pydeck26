"""Image acquisition, off-Tk preview preparation, cancellation, and durable records."""

from io import BytesIO
import json
from threading import Event, current_thread

from PIL import Image
import pytest

from pydeck26 import disk, image, machine, main, workspace
from test_machines import project, receive, send, state, stop


def create_image_panel(commands):
    send({"type": "CREATE_IMAGE", "position-id": "overview/column-1"})
    view = state(commands, lambda view: view["status"] == "Project state saved.")
    return view["documents"]["workspace"]["positions"]["overview/column-1"]["panel-id"]


def wait_for_asset(commands, panel_id):
    return state(commands, lambda view: bool(view["documents"]["workspace"]["panels"][panel_id]["image-asset"]))["documents"]["workspace"]["panels"][panel_id]["image-asset"]


@pytest.mark.parametrize("format,extension", [("PNG", ".png"), ("JPEG", ".jpg"), ("GIF", ".gif")])
def test_import_and_preview_supported_formats(project, format, extension, monkeypatch):
    root, commands = project
    source = root / "a source with spaces.bin"
    Image.new("RGB", (120, 60), "red").save(source, format=format)
    original = source.read_bytes()
    observed = []
    prepare = image.prepare_preview

    def observed_preview(data, bounds):
        observed.append(current_thread().name)
        return prepare(data, bounds)

    monkeypatch.setattr(image, "prepare_preview", observed_preview)
    panel_id = create_image_panel(commands)
    send({"type": "IMPORT_IMAGE", "panel-id": panel_id, "source": {"kind": "file", "path": str(source)}})
    asset = wait_for_asset(commands, panel_id)
    assert asset.endswith(extension)
    assert disk.get_image_asset_path(asset).read_bytes() == original
    send({"type": "IMAGE_PREVIEW", "panel-id": panel_id, "image-asset": asset,
          "request-id": "small", "width": 30, "height": 20})
    preview = receive(commands, lambda command: command["type"] == "SET_IMAGE_PREVIEW")
    assert (preview["width"], preview["height"]) == (30, 15)
    assert len(preview["pixels"]) == 30 * 15 * 4
    send({"type": "IMAGE_PREVIEW", "panel-id": panel_id, "image-asset": asset,
          "request-id": "large", "width": 1000, "height": 1000})
    preview = receive(commands, lambda command: command["type"] == "SET_IMAGE_PREVIEW")
    assert (preview["width"], preview["height"]) == (120, 60)
    assert observed == ["PyDeck IMAGE", "PyDeck IMAGE"]
    stroke = {"points": [[0.1, 0.2], [0.8, 0.9]], "color": "#FF3030", "width": 0.03}
    send({"type": "IMAGE_STROKE_ADDED", "panel-id": panel_id, "image-asset": asset, "stroke": stroke})
    stop(commands)
    assert source.read_bytes() == original
    stored = json.loads((root / "db/pydeck26/workspace.json").read_text())
    assert stored["panels"][panel_id]["image-strokes"] == [stroke]
    assert "pixels" not in stored["panels"][panel_id]
    commands = main.start_project_workers(root)
    restored = state(commands, lambda view: view["ready"])
    assert restored["documents"]["workspace"]["panels"][panel_id]["image-asset"] == asset
    send({"type": "CLEAR_IMAGE", "panel-id": panel_id})
    stop(commands)
    assert disk.get_image_asset_path(asset).read_bytes() == original
    assert json.loads((root / "db/pydeck26/workspace.json").read_text())["panels"][panel_id]["image-strokes"] == []


def test_clipboard_pixels_are_acquired_in_image_worker(project, monkeypatch):
    root, commands = project
    observed = []

    def clipboard():
        observed.append(current_thread().name)
        return Image.new("RGB", (25, 10), "blue")

    monkeypatch.setattr(image.ImageGrab, "grabclipboard", clipboard)
    panel_id = create_image_panel(commands)
    send({"type": "IMPORT_IMAGE", "panel-id": panel_id, "source": {"kind": "clipboard"}})
    asset = wait_for_asset(commands, panel_id)
    assert asset.endswith(".png")
    assert observed == ["PyDeck IMAGE"]
    assert Image.open(disk.get_image_asset_path(asset)).size == (25, 10)


@pytest.mark.parametrize("source_kind", ["missing", "broken", "bmp", "empty-clipboard"])
def test_bad_input_is_panel_error_not_worker_death(project, source_kind, monkeypatch):
    root, commands = project
    panel_id = create_image_panel(commands)
    source = root / "input"
    if source_kind == "broken":
        source.write_bytes(b"not an image")
    elif source_kind == "bmp":
        Image.new("RGB", (5, 5)).save(source, format="BMP")
    elif source_kind == "empty-clipboard":
        monkeypatch.setattr(image.ImageGrab, "grabclipboard", lambda: None)
    request = {"kind": "clipboard"} if source_kind == "empty-clipboard" else {"kind": "file", "path": str(source)}
    send({"type": "IMPORT_IMAGE", "panel-id": panel_id, "source": request})
    view = state(commands, lambda view: bool(view["image-states"].get(panel_id, {}).get("error")))
    assert view["documents"]["workspace"]["panels"][panel_id]["image-asset"] is None
    assert not machine.fatal.is_set()


@pytest.mark.parametrize("action", ["CLEAR_IMAGE", "DELETE_PANEL"])
def test_late_import_cannot_restore_cleared_or_deleted_panel(project, action, monkeypatch):
    root, commands = project
    source = root / "source.png"
    Image.new("RGB", (10, 10)).save(source)
    panel_id = create_image_panel(commands)
    started, release = Event(), Event()
    original = disk.HANDLERS["WRITE_IMAGE_ASSET"]

    def held_write():
        started.set()
        assert release.wait(5)
        original()

    monkeypatch.setitem(disk.HANDLERS, "WRITE_IMAGE_ASSET", held_write)
    send({"type": "IMPORT_IMAGE", "panel-id": panel_id, "source": {"kind": "file", "path": str(source)}})
    assert started.wait(5)
    send({"type": action, "panel-id": panel_id})
    state(commands, lambda view: not view["image-states"].get(panel_id, {}).get("busy"))
    release.set()
    stop(commands)
    panels = json.loads((root / "db/pydeck26/workspace.json").read_text())["panels"]
    assert panel_id not in panels if action == "DELETE_PANEL" else panels[panel_id]["image-asset"] is None


def test_asset_paths_cannot_escape_storage(project):
    with pytest.raises(ValueError):
        disk.get_image_asset_path("../../README.md")


def test_gif_preview_uses_first_frame():
    contents = BytesIO()
    first = Image.new("RGB", (5, 5), "red")
    first.save(contents, format="GIF", save_all=True, append_images=[Image.new("RGB", (5, 5), "blue")])
    result = image.prepare_preview(contents.getvalue(), (5, 5))
    assert result["pixels"][:4] == bytes([255, 0, 0, 255])


def test_image_worker_failure_stops_all_workers(project, monkeypatch):
    root, commands = project
    panel_id = create_image_panel(commands)

    def fail():
        raise RuntimeError("injected image worker failure")

    monkeypatch.setitem(image.HANDLERS, "IMPORT_IMAGE", fail)
    send({"type": "IMPORT_IMAGE", "panel-id": panel_id, "source": {"kind": "clipboard"}})
    assert machine.fatal.wait(5)


@pytest.mark.parametrize("action", ["CLEAR_IMAGE", "DELETE_PANEL"])
def test_late_preview_is_discarded_after_clear_or_delete(project, action, monkeypatch):
    root, commands = project
    source = root / "source.png"
    Image.new("RGB", (50, 25)).save(source)
    panel_id = create_image_panel(commands)
    send({"type": "IMPORT_IMAGE", "panel-id": panel_id, "source": {"kind": "file", "path": str(source)}})
    asset = wait_for_asset(commands, panel_id)
    started, release = Event(), Event()
    original = image.HANDLERS["LOAD_PREVIEW"]

    def held_preview():
        started.set()
        assert release.wait(5)
        original()

    monkeypatch.setitem(image.HANDLERS, "LOAD_PREVIEW", held_preview)
    send({"type": "IMAGE_PREVIEW", "panel-id": panel_id, "image-asset": asset,
          "request-id": "obsolete", "width": 30, "height": 30})
    assert started.wait(5)
    send({"type": action, "panel-id": panel_id})
    state(commands, lambda view: panel_id not in view["documents"]["workspace"]["panels"]
          or view["documents"]["workspace"]["panels"][panel_id]["image-asset"] is None)
    release.set()
    seen = []
    send({"type": "SHUTDOWN"})

    def completed(command):
        seen.append(command)
        return command["type"] == "SHUTDOWN_COMPLETE"

    receive(commands, completed)
    main.finish_worker_shutdown()
    assert all(command["type"] != "SET_IMAGE_PREVIEW" for command in seen)


def test_preview_applies_exif_orientation():
    contents = BytesIO()
    source = Image.new("RGB", (80, 40), "green")
    exif = source.getexif()
    exif[274] = 6
    source.save(contents, format="JPEG", exif=exif)
    result = image.prepare_preview(contents.getvalue(), (20, 40))
    assert (result["width"], result["height"]) == (20, 40)
