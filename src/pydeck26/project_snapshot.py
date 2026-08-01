"""Read the inspectable facts of one python-2026-03 project folder."""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_MARKERS = [
    "zoo-project.json",
    "pyproject.toml",
    "README.md",
    "db",
    "docs",
    "docs/raw",
    "docs/code",
    "docs/architecture",
    "examples",
    "guitests",
    "src",
    "tests",
]


def read_project_snapshot(root: Path) -> dict:
    """Return a fault-tolerant, display-ready view of one project root."""
    root = root.expanduser().resolve()
    snapshot = {
        "root": str(root),
        "exists": root.is_dir(),
        "identity": {},
        "package": {},
        "markers": [],
        "raw_documents": [],
        "problems": [],
    }
    if not snapshot["exists"]:
        snapshot["problems"].append("The selected folder does not exist.")
        return snapshot

    read_zoo_project_identity(root, snapshot)
    read_python_packaging_identity(root, snapshot)
    list_project_markers(root, snapshot)
    list_raw_documents(root, snapshot)
    return snapshot


def read_zoo_project_identity(root: Path, snapshot: dict) -> None:
    """Read Zoo identity without making malformed metadata fatal."""
    path = root / "zoo-project.json"
    if not path.is_file():
        return
    try:
        snapshot["identity"] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        snapshot["problems"].append(f"Could not read zoo-project.json: {exc}")


def read_python_packaging_identity(root: Path, snapshot: dict) -> None:
    """Read the small TOML subset useful for first-entry orientation."""
    path = root / "pyproject.toml"
    if not path.is_file():
        return
    try:
        import tomllib

        data = tomllib.loads(path.read_text(encoding="utf-8"))
        snapshot["package"] = data.get("project", {})
    except (OSError, ValueError) as exc:
        snapshot["problems"].append(f"Could not read pyproject.toml: {exc}")


def list_project_markers(root: Path, snapshot: dict) -> None:
    """Record conventional project locations and whether each is present."""
    for marker in PROJECT_MARKERS:
        path = root / marker
        snapshot["markers"].append({
            "name": marker,
            "kind": "folder" if path.is_dir() else "file",
            "exists": path.exists(),
        })


def list_raw_documents(root: Path, snapshot: dict) -> None:
    """List raw project memory in its preserved chronological filename order."""
    raw_dir = root / "docs" / "raw"
    if not raw_dir.is_dir():
        return
    snapshot["raw_documents"] = [path.name for path in sorted(raw_dir.iterdir()) if path.is_file()]
