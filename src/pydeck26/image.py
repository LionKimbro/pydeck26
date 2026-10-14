"""Image worker: clipboard acquisition, validation, and fitted RGBA preparation."""

from io import BytesIO
from PIL import Image, ImageGrab, ImageOps, UnidentifiedImageError

from . import machine, mobile_stacks as ms

FORMATS = {"JPEG": ".jpg", "PNG": ".png", "GIF": ".gif"}
INPUT_ERRORS = (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError)


def finish_error(error):
    ms.stack()["registers"].pop("image-bytes", None)
    ms.set_register(("image-result", {"status": "error", "error": str(error)}))


def continue_through_disk(entry, continuation):
    machine.continue_with_frames([
        {"machine": "IMAGE", "entry": continuation}, {"machine": "DISK", "entry": entry},
    ])


def inspect_image(data):
    with Image.open(BytesIO(data)) as decoded:
        if decoded.format not in FORMATS:
            raise ValueError("Choose a JPEG, PNG, or GIF image")
        decoded.seek(0)
        decoded.load()
        return FORMATS[decoded.format]


def prepare_preview(data, bounds):
    with Image.open(BytesIO(data)) as decoded:
        if decoded.format not in FORMATS:
            raise ValueError("Unsupported stored image format")
        decoded.seek(0)
        decoded.load()
        prepared = ImageOps.exif_transpose(decoded).convert("RGBA")
        prepared.thumbnail((max(1, bounds[0]), max(1, bounds[1])), Image.Resampling.LANCZOS)
        return {"status": "ok", "width": prepared.width, "height": prepared.height, "pixels": prepared.tobytes()}


def handle_when_image_receives_import():
    source = ms.get_register("source")
    if source["kind"] == "file":
        continue_through_disk("READ_IMAGE_SOURCE", "SOURCE_READ")
        return
    try:
        if source["kind"] != "clipboard":
            raise ValueError("Unknown image source")
        contents = ImageGrab.grabclipboard()
        if isinstance(contents, list) and len(contents) == 1:
            ms.set_register(("source", {"kind": "file", "path": contents[0]}))
            continue_through_disk("READ_IMAGE_SOURCE", "SOURCE_READ")
            return
        if not isinstance(contents, Image.Image):
            raise ValueError("The clipboard must contain an image or one image file")
        with BytesIO() as destination:
            contents.save(destination, format="PNG")
            ms.set_register(("image-bytes", destination.getvalue()))
        ms.set_register(("image-error", None))
    except INPUT_ERRORS as error:
        finish_error(error)
        return
    handle_when_image_source_has_been_read()


def handle_when_image_source_has_been_read():
    if ms.get_register("image-error"):
        finish_error(ms.get_register("image-error"))
        return
    try:
        extension = inspect_image(ms.get_register("image-bytes"))
    except INPUT_ERRORS as error:
        finish_error(error)
        return
    ms.set_register(("image-extension", extension))
    continue_through_disk("WRITE_IMAGE_ASSET", "ASSET_WRITTEN")


def handle_when_image_asset_has_been_written():
    if ms.get_register("image-error"):
        finish_error(ms.get_register("image-error"))
        return
    ms.stack()["registers"].pop("image-bytes", None)
    ms.set_register(("image-result", {"status": "ok", "image-asset": ms.get_register("image-asset")}))


def handle_when_image_receives_preview_request():
    continue_through_disk("READ_IMAGE_ASSET", "PREVIEW_READ")


def handle_when_image_preview_has_been_read():
    if ms.get_register("image-error"):
        finish_error(ms.get_register("image-error"))
        return
    data = ms.stack()["registers"].pop("image-bytes")
    try:
        result = prepare_preview(data, (ms.get_register("width"), ms.get_register("height")))
    except INPUT_ERRORS as error:
        finish_error(error)
        return
    ms.set_register(("image-result", result))


HANDLERS = {"IMPORT_IMAGE": handle_when_image_receives_import,
            "SOURCE_READ": handle_when_image_source_has_been_read,
            "ASSET_WRITTEN": handle_when_image_asset_has_been_written,
            "LOAD_PREVIEW": handle_when_image_receives_preview_request,
            "PREVIEW_READ": handle_when_image_preview_has_been_read}
