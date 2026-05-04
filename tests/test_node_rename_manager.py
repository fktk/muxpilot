"""Tests for muxpilot.controllers.NodeRenameManager."""

from __future__ import annotations

from unittest.mock import MagicMock

from muxpilot.controllers import NodeRenameManager
from muxpilot.models import SessionInfo, WindowInfo, PaneInfo


def make_node_data(node_type: str, session_name="work", window_index=0, pane_index=0):
    """Create node_data tuple for NodeRenameManager.start()."""
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


class TestPaneRename:
    def test_start_returns_pane_title(self) -> None:
        client = MagicMock()
        ctrl = NodeRenameManager(client)
        data = make_node_data("pane", session_name="myproject", window_index=2, pane_index=1)
        data[3].pane_title = "existing-title"
        current = ctrl.start(data)
        assert ctrl.key == "myproject.2.1"
        assert ctrl._target_id == "%0"
        assert current == "existing-title"

    def test_start_none_returns_none(self) -> None:
        client = MagicMock()
        ctrl = NodeRenameManager(client)
        assert ctrl.start(None) is None

    def test_finish_calls_set_pane_title(self) -> None:
        client = MagicMock()
        client.set_pane_title.return_value = True
        ctrl = NodeRenameManager(client)
        ctrl.start(make_node_data("pane", session_name="work"))
        result = ctrl.finish("New Title")
        assert result == "work.0.0"
        client.set_pane_title.assert_called_once_with("%0", "New Title")

    def test_finish_empty_calls_set_pane_title(self) -> None:
        client = MagicMock()
        client.set_pane_title.return_value = True
        ctrl = NodeRenameManager(client)
        ctrl.start(make_node_data("pane", session_name="work"))
        result = ctrl.finish("")
        assert result == "work.0.0"
        client.set_pane_title.assert_called_once_with("%0", "")

    def test_finish_without_start_is_noop(self) -> None:
        client = MagicMock()
        ctrl = NodeRenameManager(client)
        assert ctrl.finish("x") is None
        client.set_pane_title.assert_not_called()

    def test_cancel_clears_key_without_saving(self) -> None:
        client = MagicMock()
        ctrl = NodeRenameManager(client)
        ctrl.start(make_node_data("pane", session_name="work"))
        ctrl.cancel()
        assert ctrl.key is None
        assert ctrl._target_id is None


class TestWindowRename:
    def test_start_returns_window_name(self) -> None:
        client = MagicMock()
        ctrl = NodeRenameManager(client)
        data = make_node_data("window", session_name="myproject", window_index=2)
        data[2].window_name = "existing-window"
        current = ctrl.start(data)
        assert ctrl.key == "myproject.2"
        assert ctrl._target_id == "@0"
        assert current == "existing-window"

    def test_finish_calls_rename_window(self) -> None:
        client = MagicMock()
        client.rename_window.return_value = True
        ctrl = NodeRenameManager(client)
        ctrl.start(make_node_data("window", session_name="work"))
        result = ctrl.finish("New Window")
        assert result == "work.0"
        client.rename_window.assert_called_once_with("@0", "New Window")

    def test_finish_empty_calls_rename_window(self) -> None:
        """Empty string is allowed for windows (tmux reverts to auto-naming)."""
        client = MagicMock()
        client.rename_window.return_value = True
        ctrl = NodeRenameManager(client)
        ctrl.start(make_node_data("window", session_name="work"))
        result = ctrl.finish("")
        assert result == "work.0"
        client.rename_window.assert_called_once_with("@0", "")


class TestSessionRename:
    def test_start_returns_session_name(self) -> None:
        client = MagicMock()
        ctrl = NodeRenameManager(client)
        data = make_node_data("session", session_name="myproject")
        current = ctrl.start(data)
        assert ctrl.key == "myproject"
        assert ctrl._target_id == "$0"
        assert current == "myproject"

    def test_finish_calls_rename_session(self) -> None:
        client = MagicMock()
        client.rename_session.return_value = True
        ctrl = NodeRenameManager(client)
        ctrl.start(make_node_data("session", session_name="work"))
        result = ctrl.finish("New Session")
        assert result == "work"
        client.rename_session.assert_called_once_with("$0", "New Session")

    def test_finish_empty_ignored_for_session(self) -> None:
        """Empty string is ignored for sessions (tmux does not allow empty session names)."""
        client = MagicMock()
        client.rename_session.return_value = True
        ctrl = NodeRenameManager(client)
        ctrl.start(make_node_data("session", session_name="work"))
        result = ctrl.finish("")
        assert result is None
        client.rename_session.assert_not_called()


class TestApplyIsNoop:
    def test_apply_is_noop(self) -> None:
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
        ctrl = NodeRenameManager(client)
        ctrl.apply(tree)

        assert tree.sessions[0].custom_label == ""
        assert tree.sessions[0].windows[0].custom_label == ""
        assert tree.sessions[0].windows[0].panes[0].custom_label == ""
