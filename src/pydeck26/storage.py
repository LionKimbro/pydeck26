"""Project-local Whiteboard storage for PyDeck 26."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import json
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
    conversations_path = get_pydeck_data_dir(root) / "conversations.json"
    if not conversations_path.exists():
        write_text_atomic(conversations_path, '{"items": []}\n')
    resources_path = get_resources_path(root)
    if not resources_path.exists():
        write_text_atomic(resources_path, '{"items": []}\n')


def load_whiteboard(root: Path) -> str:
    """Read the current Whiteboard as ordinary UTF-8 text."""
    return get_whiteboard_path(root).read_text(encoding="utf-8")


def get_conversations_path(root: Path) -> Path:
    """Return the project-local conversation register path."""
    return get_pydeck_data_dir(root) / "conversations.json"


def get_dictionary_entry_path(root: Path) -> Path:
    """Return the optional project dictionary entry path."""
    return get_pydeck_data_dir(root) / "dictionary-entry.json"


def get_ideas_path(root: Path) -> Path:
    """Return the optional project ideas register path."""
    return root / "db" / "ideas.json"


def get_resources_path(root: Path) -> Path:
    """Return the PyDeck-owned curated project resources register path."""
    return get_pydeck_data_dir(root) / "resources.json"


def load_ideas(root: Path) -> dict:
    """Read ideas without creating an empty file during startup."""
    path = get_ideas_path(root)
    if not path.is_file():
        return {"items": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("ideas.json must contain a JSON object")
    if not isinstance(data.get("items"), list):
        data["items"] = []
    return data


def save_ideas(root: Path, document: dict) -> None:
    """Write the complete ideas register and preserve unrecognized fields."""
    write_text_atomic(get_ideas_path(root), f"{json.dumps(document, indent=2, ensure_ascii=False)}\n")


def load_resources(root: Path) -> dict:
    """Read the ordered curated resource list without creating it at startup."""
    path = get_resources_path(root)
    if not path.is_file():
        return {"items": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("resources.json must contain a JSON object")
    if not isinstance(data.get("items"), list):
        data["items"] = []
    return data


def save_resources(root: Path, document: dict) -> None:
    """Write the ordered curated resource list without touching referenced files."""
    content = json.dumps(document, indent=2, ensure_ascii=False)
    write_text_atomic(get_resources_path(root), f"{content}\n")


def load_dictionary_entry(root: Path) -> dict | None:
    """Read the optional dictionary entry without creating a starter file."""
    path = get_dictionary_entry_path(root)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("dictionary-entry.json must contain a JSON object")
    return data


def save_dictionary_entry(root: Path, document: dict) -> None:
    """Persist the complete dictionary entry, preserving its unknown fields."""
    content = json.dumps(document, indent=2, ensure_ascii=False)
    write_text_atomic(get_dictionary_entry_path(root), f"{content}\n")


def load_conversations(root: Path) -> dict:
    """Read the conversation register while tolerating its absence before initialization."""
    path = get_conversations_path(root)
    if not path.is_file():
        return {"items": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("conversations.json must contain a JSON object")
    if not isinstance(data.get("items"), list):
        data["items"] = []
    return data


def save_conversations(root: Path, document: dict) -> None:
    """Persist the complete conversation document, including unfamiliar preserved fields."""
    content = json.dumps(document, indent=2, ensure_ascii=False)
    write_text_atomic(get_conversations_path(root), f"{content}\n")


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
