from pathlib import Path

import pytest

from pydeck26.storage import (
    get_conversations_path,
    get_dictionary_entry_path,
    get_resources_path,
    get_snapshot_dir,
    get_whiteboard_path,
    initialize_project,
    list_snapshots,
    load_whiteboard,
    save_snapshot,
    save_conversations,
    save_dictionary_entry,
    save_resources,
    save_whiteboard,
)


def test_initialize_project_creates_only_pydeck_owned_seed_files(tmp_path: Path) -> None:
    initialize_project(tmp_path)

    assert get_whiteboard_path(tmp_path).read_text(encoding="utf-8") == ""
    assert (tmp_path / "db" / "pydeck26" / "settings.json").read_text(encoding="utf-8") == "{}\n"
    assert get_snapshot_dir(tmp_path).is_dir()
    assert get_conversations_path(tmp_path).read_text(encoding="utf-8") == '{"items": []}\n'
    assert get_resources_path(tmp_path).read_text(encoding="utf-8") == '{"items": []}\n'


def test_save_resources_preserves_explicit_item_order(tmp_path: Path) -> None:
    initialize_project(tmp_path)
    document = {"items": [{"path": "docs/raw/", "filename": "020__architecture.md", "hook": "current architecture"}, {"path": "db/", "filename": "rules.md", "hook": "agent instructions"}]}

    save_resources(tmp_path, document)

    text = get_resources_path(tmp_path).read_text(encoding="utf-8")
    assert text.index('"020__architecture.md"') < text.index('"rules.md"')


def test_save_conversations_preserves_unfamiliar_fields(tmp_path: Path) -> None:
    initialize_project(tmp_path)
    document = {"items": [{"id": "one", "title": "First", "custom": "keep"}], "future-field": {"keep": True}}

    save_conversations(tmp_path, document)

    assert '"future-field"' in get_conversations_path(tmp_path).read_text(encoding="utf-8")
    assert '"custom": "keep"' in get_conversations_path(tmp_path).read_text(encoding="utf-8")


def test_dictionary_entry_is_optional_until_explicitly_saved(tmp_path: Path) -> None:
    initialize_project(tmp_path)

    assert not get_dictionary_entry_path(tmp_path).exists()

    save_dictionary_entry(tmp_path, {"identity": {"title": "A title"}, "extension": "keep"})

    text = get_dictionary_entry_path(tmp_path).read_text(encoding="utf-8")
    assert '"extension": "keep"' in text


def test_initialize_project_does_not_overwrite_existing_whiteboard(tmp_path: Path) -> None:
    initialize_project(tmp_path)
    save_whiteboard(tmp_path, "still here")

    initialize_project(tmp_path)

    assert load_whiteboard(tmp_path) == "still here"


def test_snapshots_are_newest_first_and_never_overwrite_same_second(tmp_path: Path, monkeypatch) -> None:
    initialize_project(tmp_path)
    monkeypatch.setattr("pydeck26.storage.datetime", FixedDateTime)

    newest = save_snapshot(tmp_path, "first thought")
    assert newest.name == "2026-08-01-010203.txt"
    assert list_snapshots(tmp_path) == [newest]

    with pytest.raises(FileExistsError):
        save_snapshot(tmp_path, "would overwrite history")


class FixedDateTime:
    """A one-purpose datetime test double with a stable local timestamp."""

    @classmethod
    def now(cls):
        return cls()

    def strftime(self, pattern: str) -> str:
        assert pattern == "%Y-%m-%d-%H%M%S.txt"
        return "2026-08-01-010203.txt"
