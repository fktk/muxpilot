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
        pane_title="",
    )
    return (node_type, session, window, pane)


class TestRenameControllerPaneTitle:
    """RenameController sets tmux pane_title directly via TmuxClient."""

    def test_start_returns_pane_title(self) -> None:
        from unittest.mock import MagicMock
        client = MagicMock()
        ctrl = RenameController(client)
        data = make_node_data("pane", session_name="myproject", window_index=2, pane_index=1)
        data[3].pane_title = "existing-title"
        current = ctrl.start(data)
        assert ctrl.key == "myproject.2.1"
        assert ctrl._pane_id == "%0"
        assert current == "existing-title"

    def test_start_none_returns_none(self) -> None:
        from unittest.mock import MagicMock
        client = MagicMock()
        ctrl = RenameController(client)
        assert ctrl.start(None) is None

    def test_finish_calls_set_pane_title(self) -> None:
        from unittest.mock import MagicMock
        client = MagicMock()
        client.set_pane_title.return_value = True
        ctrl = RenameController(client)
        ctrl.start(make_node_data("pane", session_name="work"))
        result = ctrl.finish("New Title")
        assert result == "work.0.0"
        client.set_pane_title.assert_called_once_with("%0", "New Title")

    def test_finish_empty_calls_set_pane_title(self) -> None:
        from unittest.mock import MagicMock
        client = MagicMock()
        client.set_pane_title.return_value = True
        ctrl = RenameController(client)
        ctrl.start(make_node_data("pane", session_name="work"))
        result = ctrl.finish("")
        assert result == "work.0.0"
        client.set_pane_title.assert_called_once_with("%0", "")

    def test_finish_without_start_is_noop(self) -> None:
        from unittest.mock import MagicMock
        client = MagicMock()
        ctrl = RenameController(client)
        assert ctrl.finish("x") is None
        client.set_pane_title.assert_not_called()

    def test_cancel_clears_key_without_saving(self) -> None:
        from unittest.mock import MagicMock
        client = MagicMock()
        ctrl = RenameController(client)
        ctrl.start(make_node_data("pane", session_name="work"))
        ctrl.cancel()
        assert ctrl.key is None
        assert ctrl._pane_id is None

    def test_apply_is_noop(self) -> None:
        from unittest.mock import MagicMock
        from muxpilot.models import TmuxTree
        from conftest import make_session, make_window, make_pane

        tree = TmuxTree(sessions=[
            make_session(session_name="work", session_id="$0", windows=[
                make_window(window_name="editor", window_index=0, panes=[
                    make_pane(pane_id="%0", pane_index=0),
                ])
            ])
        ])

        client = MagicMock()
        ctrl = RenameController(client)
        ctrl.apply(tree)

        assert tree.sessions[0].custom_label == ""
        assert tree.sessions[0].windows[0].custom_label == ""
        assert tree.sessions[0].windows[0].panes[0].custom_label == ""
