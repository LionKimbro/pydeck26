from pathlib import Path

from pydeck26.project_snapshot import read_project_snapshot


def test_read_project_snapshot_reports_python_2026_03_markers(tmp_path: Path) -> None:
    (tmp_path / "docs" / "raw").mkdir(parents=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "zoo-project.json").write_text('{"name": "small-world", "repo-type": "python-2026-03"}', encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "small-world"\n', encoding="utf-8")
    (tmp_path / "docs" / "raw" / "001__first-thought.md").write_text("kept", encoding="utf-8")

    snapshot = read_project_snapshot(tmp_path)

    assert snapshot["exists"] is True
    assert snapshot["identity"]["name"] == "small-world"
    assert snapshot["package"]["name"] == "small-world"
    assert snapshot["raw_documents"] == ["001__first-thought.md"]
    assert {item["name"] for item in snapshot["markers"] if item["exists"]} >= {"zoo-project.json", "pyproject.toml", "docs", "docs/raw", "src"}


def test_read_project_snapshot_reports_missing_folder(tmp_path: Path) -> None:
    snapshot = read_project_snapshot(tmp_path / "not-here")

    assert snapshot["exists"] is False
    assert snapshot["problems"] == ["The selected folder does not exist."]
