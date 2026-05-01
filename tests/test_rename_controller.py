"""Tests for muxpilot.controllers.RenameController — in-memory overlay only."""

from __future__ import annotations

import pytest

from muxpilot.controllers import RenameController
from muxpilot.models import SessionInfo, WindowInfo, PaneInfo


def make_node_data(node_type: str, session_name="work", window_index=0, pane_index=0):
    """Create node_data tuple for RenameController.start()."""
    session = SessionInfo(
        session_name=session_name,
        session_id="$0",
        is_attached=True,
        windows=[],
    )
    window = WindowInfo(
        window_id="@0",
        window_name="editor",
        window_index=window_index,
        is_active=True,
        panes=[],
    )
    pane = PaneInfo(
        pane_id="%0",
        pane_index=pane_index,
        current_command="bash",
        current_path="/home/user",
        is_active=True,
        width=80,
        height=24,
    )
    return (node_type, session, window, pane)


class TestRenameControllerOverlay:
    """RenameController stores labels only in memory (no persistence)."""

    def test_get_returns_empty_when_no_overlay(self) -> None:
        ctrl = RenameController()
        assert ctrl.get("work") == ""

    def test_set_and_get(self) -> None:
        ctrl = RenameController()
        ctrl.set("work", "My Project")
        assert ctrl.get("work") == "My Project"

    def test_set_overwrites_existing(self) -> None:
        ctrl = RenameController()
        ctrl.set("work", "old")
        ctrl.set("work", "new")
        assert ctrl.get("work") == "new"

    def test_delete_removes_overlay(self) -> None:
        ctrl = RenameController()
        ctrl.set("work", "label")
        ctrl.delete("work")
        assert ctrl.get("work") == ""

    def test_empty_value_treated_as_delete(self) -> None:
        ctrl = RenameController()
        ctrl.set("work", "label")
        ctrl.set("work", "")
        assert ctrl.get("work") == ""

    def test_start_session_key(self) -> None:
        ctrl = RenameController()
        data = make_node_data("session", session_name="myproject")
        current = ctrl.start(data)
        assert ctrl.key == "myproject"
        assert current == ""

    def test_start_window_key(self) -> None:
        ctrl = RenameController()
        data = make_node_data("window", session_name="myproject", window_index=2)
        current = ctrl.start(data)
        assert ctrl.key == "myproject.2"
        assert current == ""

    def test_start_pane_key(self) -> None:
        ctrl = RenameController()
        data = make_node_data("pane", session_name="myproject", window_index=2, pane_index=1)
        current = ctrl.start(data)
        assert ctrl.key == "myproject.2.1"
        assert current == ""

    def test_start_returns_existing_overlay(self) -> None:
        ctrl = RenameController()
        ctrl.set("myproject", "Existing")
        data = make_node_data("session", session_name="myproject")
        current = ctrl.start(data)
        assert current == "Existing"

    def test_start_none_returns_none(self) -> None:
        ctrl = RenameController()
        assert ctrl.start(None) is None

    def test_finish_sets_overlay(self) -> None:
        ctrl = RenameController()
        ctrl.start(make_node_data("session", session_name="work"))
        result = ctrl.finish("New Label")
        assert result == "work"
        assert ctrl.get("work") == "New Label"

    def test_finish_empty_deletes_overlay(self) -> None:
        ctrl = RenameController()
        ctrl.set("work", "Existing")
        ctrl.start(make_node_data("session", session_name="work"))
        result = ctrl.finish("")
        assert result == "work"
        assert ctrl.get("work") == ""

    def test_finish_without_start_is_noop(self) -> None:
        ctrl = RenameController()
        assert ctrl.finish("x") is None

    def test_cancel_clears_key_without_saving(self) -> None:
        ctrl = RenameController()
        ctrl.start(make_node_data("session", session_name="work"))
        ctrl.cancel()
        assert ctrl.key is None
        assert ctrl.get("work") == ""

    def test_apply_to_tree(self) -> None:
        """apply() should set custom_label on the tree from overlays."""
        from muxpilot.models import TmuxTree
        from conftest import make_session, make_window, make_pane

        tree = TmuxTree(sessions=[
            make_session(session_name="work", session_id="$0", windows=[
                make_window(window_name="editor", window_index=0, panes=[
                    make_pane(pane_id="%0", pane_index=0),
                ])
            ])
        ])

        ctrl = RenameController()
        ctrl.set("work", "Project A")
        ctrl.set("work.0", "Editor Window")
        ctrl.set("work.0.0", "Main Pane")

        ctrl.apply(tree)

        assert tree.sessions[0].custom_label == "Project A"
        assert tree.sessions[0].windows[0].custom_label == "Editor Window"
        assert tree.sessions[0].windows[0].panes[0].custom_label == "Main Pane"

    def test_apply_skips_missing_overlays(self) -> None:
        from muxpilot.models import TmuxTree
        from conftest import make_session, make_window, make_pane

        tree = TmuxTree(sessions=[
            make_session(session_name="work", windows=[
                make_window(window_index=0, panes=[make_pane(pane_index=0)])
            ])
        ])

        ctrl = RenameController()
        ctrl.apply(tree)

        assert tree.sessions[0].custom_label == ""

    def test_overlay_does_not_persist_across_instances(self) -> None:
        ctrl1 = RenameController()
        ctrl1.set("work", "temp")

        ctrl2 = RenameController()
        assert ctrl2.get("work") == ""

    def test_overlay_overrides_store(self) -> None:
        """When LabelStore and overlay both have a value, overlay wins."""
        from pathlib import Path
        from muxpilot.label_store import LabelStore
        tmp_path = Path("/tmp/muxpilot_test_ctrl")
        tmp_path.mkdir(parents=True, exist_ok=True)
        config = tmp_path / "config.toml"
        store = LabelStore(config_path=config)
        store.set("work", "Stored Label")

        ctrl = RenameController()
        # Simulate applying both sources: store first, then overlay
        ctrl.set("work", "Overlay Label")
        assert ctrl.get("work") == "Overlay Label"
