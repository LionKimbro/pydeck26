"""Hosting identity, destructive layout transitions, and legal workspace boundaries."""

from copy import deepcopy

import pytest

from pydeck26 import workspace


def test_shrinking_rows_unhosts_panels_without_deleting_their_records():
    document = workspace.make_default_workspace()
    original_panels = deepcopy(document["panels"])
    workspace.apply_layout_event(document, {"type": "SET_ROW_COLUMNS", "row-id": "overview", "column-count": 1})
    workspace.validate_workspace(document)
    assert "overview/column-2" not in document["positions"]
    assert document["panels"] == original_panels
    assert "project-dictionary" not in workspace.get_hosted_panel_ids(document, "cockpit")
    workspace.apply_layout_event(document, {"type": "SET_ROW_COLUMNS", "row-id": "overview", "column-count": 3})
    assert document["positions"]["overview/column-2"]["panel-id"] is None
    assert document["rows"]["overview"]["sash-proportions"] == [1 / 3, 2 / 3]


def test_panel_can_be_shared_between_tabs_but_not_duplicated_in_one():
    document = workspace.make_default_workspace()
    workspace.apply_layout_event(document, {"type": "CREATE_TAB", "label": "Research"})
    tab_id = document["selected-tab-id"]
    row_id = workspace.get_tab(document, tab_id)["row-ids"][0]
    target = workspace.position_id(row_id, 1)
    workspace.apply_layout_event(document, {"type": "HOST_PANEL", "position-id": target, "panel-id": "project-whiteboard"})
    workspace.apply_layout_event(document, {"type": "SET_ROW_COLUMNS", "row-id": row_id, "column-count": 2})
    before = deepcopy(document)
    with pytest.raises(ValueError, match="once"):
        workspace.apply_layout_event(document, {"type": "HOST_PANEL", "position-id": workspace.position_id(row_id, 2),
                                                "panel-id": "project-whiteboard"})
    assert document == before
    workspace.validate_workspace(document)
    assert "project-whiteboard" in workspace.get_hosted_panel_ids(document, "cockpit")
    assert "project-whiteboard" in workspace.get_hosted_panel_ids(document, tab_id)


def test_removing_tabs_and_rows_preserves_unhosted_notes_and_project_records():
    document = workspace.make_default_workspace()
    workspace.apply_layout_event(document, {"type": "CREATE_TAB", "label": "Notes"})
    tab_id = document["selected-tab-id"]
    row_id = workspace.get_tab(document, tab_id)["row-ids"][0]
    target = workspace.position_id(row_id, 1)
    workspace.apply_layout_event(document, {"type": "CREATE_NOTES", "position-id": target})
    panel_id = document["positions"][target]["panel-id"]
    document["panels"][panel_id]["text"] = "keep my notes"
    workspace.apply_layout_event(document, {"type": "DELETE_ROW", "row-id": row_id})
    assert workspace.get_tab(document, tab_id)["row-ids"] == []
    workspace.apply_layout_event(document, {"type": "DELETE_TAB", "tab-id": tab_id})
    workspace.validate_workspace(document)
    assert document["panels"][panel_id]["text"] == "keep my notes"
    assert document["selected-tab-id"] == "cockpit"
    with pytest.raises(ValueError, match="at least one"):
        workspace.apply_layout_event(document, {"type": "DELETE_TAB", "tab-id": "cockpit"})


def test_reordering_rows_keeps_position_identity_and_rejects_invalid_geometry():
    document = workspace.make_default_workspace()
    slots = deepcopy(document["positions"])
    workspace.apply_layout_event(document, {"type": "MOVE_ROW", "row-id": "whiteboard", "direction": -1})
    assert document["tabs"][0]["row-ids"] == ["overview", "whiteboard", "working"]
    assert document["positions"] == slots
    before = deepcopy(document)
    for event in (
        {"type": "SET_ROW_COLUMNS", "row-id": "working", "column-count": 4},
        {"type": "SET_ROW_HEIGHT", "row-id": "working", "height": -1},
        {"type": "SET_SASH_PROPORTIONS", "row-id": "working", "proportions": [1.1]},
    ):
        with pytest.raises(ValueError):
            workspace.apply_layout_event(document, event)
        assert document == before


def test_validation_rejects_dangling_host_references():
    document = workspace.make_default_workspace()
    document["positions"]["overview/column-1"]["panel-id"] = "missing-panel"
    with pytest.raises(ValueError, match="Missing"):
        workspace.validate_workspace(document)


def test_permanent_delete_removes_notes_and_all_hosting_references():
    document = workspace.make_default_workspace()
    target = "overview/column-1"
    workspace.apply_layout_event(document, {"type": "CREATE_NOTES", "position-id": target})
    panel_id = document["positions"][target]["panel-id"]
    document["panels"][panel_id]["text"] = "delete this text"
    workspace.apply_layout_event(document, {"type": "CREATE_TAB", "label": "Shared"})
    tab = workspace.get_tab(document, document["selected-tab-id"])
    other = workspace.position_id(tab["row-ids"][0], 1)
    workspace.apply_layout_event(document, {"type": "HOST_PANEL", "position-id": other, "panel-id": panel_id})
    workspace.apply_layout_event(document, {"type": "DELETE_PANEL", "panel-id": panel_id})
    assert panel_id not in document["panels"]
    assert document["positions"][target]["panel-id"] is None
    assert document["positions"][other]["panel-id"] is None
    assert "project-structure" in document["panels"]
    workspace.validate_workspace(document)


def test_deleted_project_panel_can_be_explicitly_recreated():
    document = workspace.make_default_workspace()
    workspace.apply_layout_event(document, {"type": "DELETE_PANEL", "panel-id": "project-whiteboard"})
    assert "project-whiteboard" not in document["panels"]
    workspace.validate_workspace(document)
    workspace.apply_layout_event(document, {"type": "CREATE_PROJECT_PANEL", "position-id": "whiteboard/column-1", "panel-type": "WHITEBOARD"})
    assert document["positions"]["whiteboard/column-1"]["panel-id"] == "project-whiteboard"
    workspace.validate_workspace(document)
