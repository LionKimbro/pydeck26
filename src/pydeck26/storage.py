"""Project-local Whiteboard storage for PyDeck 26."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import tempfile


def get_pydeck_data_dir(root: Path) -> Path:
    """Return PyDeck's project-local working-data directory."""
    return root / "db" / "pydeck26"


def get_whiteboard_path(root: Path) -> Path:
    """Return the mutable current Whiteboard path."""
    return get_pydeck_data_dir(root) / "whiteboard.txt"


def get_snapshot_dir(root: Path) -> Path:
    """Return the historical Whiteboard snapshot directory."""
    return root / "docs" / "whiteboard"


def is_initialized(root: Path) -> bool:
    """Say whether the minimum PyDeck working territory exists."""
    return get_pydeck_data_dir(root).is_dir()


def initialize_project(root: Path) -> None:
    """Create PyDeck-owned paths and seed files without overwriting data."""
    get_pydeck_data_dir(root).mkdir(parents=True, exist_ok=True)
    get_snapshot_dir(root).mkdir(parents=True, exist_ok=True)
    get_whiteboard_path(root).touch(exist_ok=True)
    settings_path = get_pydeck_data_dir(root) / "settings.json"
    if not settings_path.exists():
        write_text_atomic(settings_path, "{}\n")


def load_whiteboard(root: Path) -> str:
    """Read the current Whiteboard as ordinary UTF-8 text."""
    return get_whiteboard_path(root).read_text(encoding="utf-8")


def save_whiteboard(root: Path, text: str) -> None:
    """Reliably replace the mutable current Whiteboard text."""
    write_text_atomic(get_whiteboard_path(root), text)


def list_snapshots(root: Path) -> list[Path]:
    """Return snapshot paths newest-first, preserving filename chronology."""
    snapshot_dir = get_snapshot_dir(root)
    if not snapshot_dir.is_dir():
        return []
    return sorted(snapshot_dir.glob("*.txt"), reverse=True)


def save_snapshot(root: Path, text: str) -> Path:
    """Write one immutable timestamped snapshot without overwriting history."""
    filename = datetime.now().strftime("%Y-%m-%d-%H%M%S.txt")
    path = get_snapshot_dir(root) / filename
    if path.exists():
        raise FileExistsError(f"A snapshot already exists for this second: {filename}")
    write_new_text(path, text)
    return path


def read_snapshot(path: Path) -> str:
    """Read one historical snapshot without modifying it."""
    return path.read_text(encoding="utf-8")


def format_snapshot_time(path: Path) -> str:
    """Turn the timestamped snapshot filename into a readable local time."""
    moment = datetime.strptime(path.stem, "%Y-%m-%d-%H%M%S")
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def write_text_atomic(path: Path, text: str) -> None:
    """Replace a mutable text file atomically and preserve UTF-8 line breaks."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as temporary_file:
            temporary_file.write(text)
        os.replace(temporary_name, path)
    except BaseException:
        if Path(temporary_name).exists():
            Path(temporary_name).unlink()
        raise


def write_new_text(path: Path, text: str) -> None:
    """Create a historical file once, failing if a name is already occupied."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as snapshot_file:
        snapshot_file.write(text)
