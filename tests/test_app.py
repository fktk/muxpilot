"""Tests for the Textual App — integration tests using App.run_test()."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from muxpilot.models import PaneStatus
from muxpilot.app import MuxpilotApp, POLL_INTERVAL_SECONDS, MAX_POLL_BACKOFF_SECONDS
from muxpilot.widgets.tree_view import TmuxTreeView

from conftest import make_mock_client, make_mock_notify_channel, make_pane, make_session, make_tree, make_window


def _patched_app(tree=None, current_pane_id=None, label_store=None, config_error=None):
    """Create a MuxpilotApp with a mocked TmuxClient/Watcher."""
    mock_client = make_mock_client(tree=tree, current_pane_id=current_pane_id)
    app = MuxpilotApp()
    app._client = mock_client
    from muxpilot.watcher import TmuxWatcher
    app._watcher = TmuxWatcher(mock_client)
    app._notify_channel = make_mock_notify_channel()
    if config_error is not None:
        app._watcher._config_error = config_error
        app._notify_config_error()
    if label_store is not None:
        app._label_store = label_store
    return app


# ============================================================================
# App startup
# ============================================================================


@pytest.mark.asyncio
async def test_app_launches():
    """App should mount all required widgets without errors."""
    from textual.widgets import Input
    app = _patched_app()
    async with app.run_test():
        assert app.query_one("#tmux-tree", TmuxTreeView) is not None
        assert app.query_one("#detail-panel") is not None
        assert app.query_one("#status-bar") is not None
        assert app.query_one("#filter-input", Input) is not None


@pytest.mark.asyncio
async def test_tree_populated_on_mount():
    """Tree should be populated with session/window/pane data on mount."""
    tree = make_tree(sessions=[
        make_session(session_name="test-sess", windows=[
            make_window(window_name="test-win", panes=[make_pane(pane_id="%0")])
        ])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test():
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        assert len(tw._pane_map) > 0


@pytest.mark.asyncio
async def test_shows_warning_when_not_in_tmux():
    """App should show a warning when launched outside a tmux session."""
    app = _patched_app()
    app._client.is_inside_tmux = MagicMock(return_value=False)
    async with app.run_test() as pilot:
        await pilot.pause(0.1)
        messages = [call.args[0] for call in app._notify_channel.send.call_args_list if call.args]
        assert any("not running inside a tmux session" in m.lower() for m in messages)


# ============================================================================
# Navigation
# ============================================================================


@pytest.mark.asyncio
async def test_navigate_self_shows_warning():
    """Activating the muxpilot's own pane should NOT call navigate_to."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%5")])])
    ])
    app = _patched_app(tree=tree, current_pane_id="%5")
    async with app.run_test():
        msg = TmuxTreeView.PaneActivated(pane_id="%5")
        await app.on_tmux_tree_view_pane_activated(msg)
        app._client.navigate_to.assert_not_called()


@pytest.mark.asyncio
async def test_navigate_to_pane():
    """Activating a different pane should call navigate_to with that pane ID."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0", is_active=False)])])
    ])
    app = _patched_app(tree=tree, current_pane_id="%99")
    async with app.run_test():
        msg = TmuxTreeView.PaneActivated(pane_id="%0")
        await app.on_tmux_tree_view_pane_activated(msg)
        app._client.navigate_to.assert_called_once_with("%0")


@pytest.mark.asyncio
async def test_back_navigation_returns_to_previous_pane():
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0"),
            make_pane(pane_id="%1"),
        ])])
    ])
    app = _patched_app(tree=tree, current_pane_id="%0")
    async with app.run_test() as pilot:
        # Jump to %1
        await app.on_tmux_tree_view_pane_activated(
            TmuxTreeView.PaneActivated(pane_id="%1")
        )
        assert app._previous_pane_id == "%0"
        # Press b to go back
        app._client.navigate_to.reset_mock()
        await pilot.press("b")
        app._client.navigate_to.assert_called_once_with("%0")


# ============================================================================
# Keyboard: quit and refresh
# ============================================================================


@pytest.mark.asyncio
async def test_quit_key():
    """Pressing q should exit the app."""
    app = _patched_app()
    async with app.run_test() as pilot:
        await pilot.press("q")
    # After context manager exits the app has stopped — just verify no exception


@pytest.mark.asyncio
async def test_refresh_key():
    """Pressing r should trigger an additional get_tree call."""
    app = _patched_app()
    async with app.run_test() as pilot:
        # Focus the tree so 'r' is handled by the app-level binding
        app.query_one("#tmux-tree").focus()
        initial_calls = app._client.get_tree.call_count
        await pilot.press("r")
        assert app._client.get_tree.call_count > initial_calls


# ============================================================================
# Filter: name filter (/ toggle)
# ============================================================================


@pytest.mark.asyncio
async def test_filter_input_toggle():
    """Pressing / should toggle filter-input visibility."""
    from textual.widgets import Input
    app = _patched_app()
    async with app.run_test() as pilot:
        fi = app.query_one("#filter-input", Input)

        # Initially hidden
        assert not fi.has_class("-active")

        # action_filter() directly — avoids key routing ambiguity
        app.action_filter()
        await pilot.pause()
        assert fi.has_class("-active")

        # Second call hides it again
        app.action_filter()
        await pilot.pause()
        assert not fi.has_class("-active")


@pytest.mark.asyncio
async def test_escape_closes_filter_input():
    """Pressing Escape should close the active filter input."""
    from textual.widgets import Input
    app = _patched_app()
    async with app.run_test() as pilot:
        await pilot.press("slash")
        assert app.query_one("#filter-input", Input).has_class("-active")
        await pilot.press("escape")
        assert not app.query_one("#filter-input", Input).has_class("-active")


# ============================================================================
# Filter: status filters (e / w / a) — call actions directly
# ============================================================================


@pytest.mark.asyncio
async def test_status_filter_error_toggle():
    """action_filter_errors should toggle ERROR filter on/off."""
    app = _patched_app()
    async with app.run_test() as pilot:
        await app.action_filter_errors()
        await pilot.pause()
        assert app._status_filter == {PaneStatus.ERROR}

        # Second call should clear the filter
        await app.action_filter_errors()
        await pilot.pause()
        assert app._status_filter is None


@pytest.mark.asyncio
async def test_status_filter_waiting():
    """action_filter_waiting should set WAITING_INPUT filter."""
    app = _patched_app()
    async with app.run_test() as pilot:
        await app.action_filter_waiting()
        await pilot.pause()
        assert app._status_filter == {PaneStatus.WAITING_INPUT}

        # Second call clears it
        await app.action_filter_waiting()
        await pilot.pause()
        assert app._status_filter is None


@pytest.mark.asyncio
async def test_filter_all_clears():
    """action_filter_all should clear both status and name filters."""
    from textual.widgets import Input
    app = _patched_app()
    async with app.run_test() as pilot:
        # Set some filter state
        await app.action_filter_errors()
        await pilot.pause()
        assert app._status_filter is not None

        # Now clear everything
        await app.action_filter_all()
        await pilot.pause()
        assert app._status_filter is None
        assert app._name_filter == ""
        fi = app.query_one("#filter-input", Input)
        assert not fi.has_class("-active")


# ============================================================================
# Cursor preservation: populate() must not reset cursor position
# ============================================================================


@pytest.mark.asyncio
async def test_cursor_preserved_after_repopulate():
    """Calling populate() again (e.g., on status events) must not reset cursor.

    This is a regression test for the bug where node._line == -1 on newly
    added nodes caused move_cursor() to snap the view to line -1 (top).
    """
    tree = make_tree(sessions=[
        make_session(session_id="$0", session_name="s0", windows=[
            make_window(window_id="@0", panes=[
                make_pane(pane_id="%0", is_active=False),
                make_pane(pane_id="%1", is_active=False),
                make_pane(pane_id="%2", is_active=False),
            ])
        ])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)

        # Navigate cursor down to %2 (third pane)
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause()

        cursor_before = tw.cursor_node

        # Simulate a poll-triggered repopulate (same tree content)
        tw.populate(tree, current_pane_id=None)
        # Wait two render cycles so call_after_refresh fires
        await pilot.pause()
        await pilot.pause()

        cursor_after = tw.cursor_node

        # Cursor must not have been reset to root/first node
        assert cursor_after is not None
        assert cursor_after != tw.root, "Cursor was reset to root after repopulate"
        # The cursor path (pane id) must match
        if cursor_before is not None:
            before_data = tw._node_data.get(cursor_before.id if cursor_before in [tw.root] else cursor_after.id)
            # Verify cursor is on the same path as before repopulate
            before_path = tw._get_node_path(cursor_before) if cursor_before else None
            after_path = tw._get_node_path(cursor_after) if cursor_after else None
            assert before_path == after_path, (
                f"Cursor path changed after repopulate: {before_path!r} → {after_path!r}"
            )


# ============================================================================
# StatusBar: icon legend display
# ============================================================================


@pytest.mark.asyncio
async def test_status_bar_shows_icon_legend():
    """StatusBar should display the icon-to-status legend."""
    from muxpilot.models import STATUS_ICONS
    from muxpilot.widgets.status_bar import StatusBar

    tree = make_tree()
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        sb = app.query_one("#status-bar", StatusBar)
        text = str(sb.render())

        # Each status icon and its label should appear
        for status, icon in STATUS_ICONS.items():
            assert icon in text, f"Icon {icon!r} for {status.value} not found in status bar"


# ============================================================================
# Keyboard: 'a' toggles collapse/expand on ALL tree nodes
# ============================================================================


@pytest.mark.asyncio
async def test_a_key_collapses_all_nodes():
    """Pressing 'a' when nodes are expanded should collapse all session/window nodes."""
    tree = make_tree(sessions=[
        make_session(session_id="$0", session_name="s0", windows=[
            make_window(window_id="@0", panes=[make_pane(pane_id="%0")]),
            make_window(window_id="@1", window_name="w1", panes=[make_pane(pane_id="%1")]),
        ]),
        make_session(session_id="$1", session_name="s1", windows=[
            make_window(window_id="@2", window_name="w2", panes=[make_pane(pane_id="%2")]),
        ]),
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)

        # All nodes should be expanded initially
        expandable = [n for n in _all_nodes(tw) if n.allow_expand and n != tw.root]
        assert all(n.is_expanded for n in expandable), "All nodes should start expanded"

        # Press 'a' → all should collapse
        await pilot.press("a")
        await pilot.pause()
        expandable = [n for n in _all_nodes(tw) if n.allow_expand and n != tw.root]
        assert all(not n.is_expanded for n in expandable), "All nodes should be collapsed after 'a'"


@pytest.mark.asyncio
async def test_a_key_expands_all_when_all_collapsed():
    """Pressing 'a' when all nodes are collapsed should expand all."""
    tree = make_tree(sessions=[
        make_session(session_id="$0", session_name="s0", windows=[
            make_window(window_id="@0", panes=[make_pane(pane_id="%0")]),
        ]),
        make_session(session_id="$1", session_name="s1", windows=[
            make_window(window_id="@1", window_name="w1", panes=[make_pane(pane_id="%1")]),
        ]),
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)

        # Collapse all first
        await pilot.press("a")
        await pilot.pause()

        # Press 'a' again → all should expand
        await pilot.press("a")
        await pilot.pause()
        expandable = [n for n in _all_nodes(tw) if n.allow_expand and n != tw.root]
        assert all(n.is_expanded for n in expandable), "All nodes should be expanded after second 'a'"


def _all_nodes(tw: TmuxTreeView):
    """Collect all tree nodes via BFS."""
    nodes = []
    queue = [tw.root]
    while queue:
        node = queue.pop(0)
        nodes.append(node)
        queue.extend(node.children)
    return nodes


# ============================================================================
# Notifications: status_changed events should NOT be sent to notify channel
# ============================================================================


@pytest.mark.asyncio
async def test_status_changed_events_not_notified():
    """status_changed events must not be sent to NotifyChannel."""
    from muxpilot.models import TmuxEvent

    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        # Simulate a status_changed event arriving via _do_refresh
        status_event = TmuxEvent(
            event_type="status_changed",
            pane_id="%0",
            old_status=PaneStatus.IDLE,
            new_status=PaneStatus.ACTIVE,
            message="%0: idle → active",
        )
        # Call the event handling code path directly
        status_bar = app.query_one("#status-bar")
        status_bar.show_event(status_event)

        # Clear prior send() calls from mount
        app._notify_channel.send.reset_mock()

        # Simulate _poll_tmux delivering a status_changed event
        from muxpilot.watcher import TmuxWatcher
        with patch.object(app._watcher, "poll", return_value=(tree, [status_event])):
            await app._poll_tmux()

        # Verify notify_channel.send was NOT called with the status message
        for call in app._notify_channel.send.call_args_list:
            if call.args:
                assert "idle" not in call.args[0].lower() and "active" not in call.args[0].lower(), \
                    f"status_changed event was notified: {call.args[0]}"


@pytest.mark.asyncio
async def test_structural_events_still_notified():
    """Structural events (pane_added, etc.) should still be sent to NotifyChannel."""
    from muxpilot.models import TmuxEvent

    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        app._notify_channel.send.reset_mock()

        structural_event = TmuxEvent(
            event_type="pane_added",
            pane_id="%1",
            message="Pane added: %1",
        )
        from muxpilot.watcher import TmuxWatcher
        with patch.object(app._watcher, "poll", return_value=(tree, [structural_event])):
            await app._poll_tmux()

        # Verify the structural event WAS notified
        messages = [call.args[0] for call in app._notify_channel.send.call_args_list if call.args]
        assert "Pane added: %1" in messages


# ============================================================================
# Kill pane (x key)
# ============================================================================


@pytest.mark.asyncio
async def test_kill_pane_key_shows_modal():
    """Pressing x on a pane node should push KillPaneModalScreen."""
    from muxpilot.screens.kill_modal import KillPaneModalScreen

    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0", is_active=False)])])
    ])
    app = _patched_app(tree=tree, current_pane_id="%99")
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause()

        app.action_kill_pane()
        await pilot.pause()

        assert isinstance(app.screen, KillPaneModalScreen)


@pytest.mark.asyncio
async def test_kill_pane_confirm_y_kills():
    """Confirming the kill modal with y should call kill_pane."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0", is_active=False)])])
    ])
    app = _patched_app(tree=tree, current_pane_id="%99")
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause()

        app.action_kill_pane()
        await pilot.pause()

        app._notify_channel.send.reset_mock()
        await pilot.press("y")
        await pilot.pause()

        app._client.kill_pane.assert_called_once_with("%0")


@pytest.mark.asyncio
async def test_kill_pane_confirm_enter_kills():
    """Confirming the kill modal with Enter should also call kill_pane."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0", is_active=False)])])
    ])
    app = _patched_app(tree=tree, current_pane_id="%99")
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause()

        app.action_kill_pane()
        await pilot.pause()

        app._notify_channel.send.reset_mock()
        await pilot.press("enter")
        await pilot.pause()

        app._client.kill_pane.assert_called_once_with("%0")


@pytest.mark.asyncio
async def test_kill_pane_cancel_n():
    """Pressing n in the kill modal should cancel without killing."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0", is_active=False)])])
    ])
    app = _patched_app(tree=tree, current_pane_id="%99")
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause()

        app.action_kill_pane()
        await pilot.pause()

        await pilot.press("n")
        await pilot.pause()

        app._client.kill_pane.assert_not_called()


@pytest.mark.asyncio
async def test_kill_pane_cancel_escape():
    """Pressing Escape in the kill modal should cancel without killing."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0", is_active=False)])])
    ])
    app = _patched_app(tree=tree, current_pane_id="%99")
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause()

        app.action_kill_pane()
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()

        app._client.kill_pane.assert_not_called()


@pytest.mark.asyncio
async def test_kill_pane_self_not_allowed():
    """Pressing x on the current (self) pane should not push the modal."""
    from muxpilot.screens.kill_modal import KillPaneModalScreen

    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%5")])])
    ])
    app = _patched_app(tree=tree, current_pane_id="%5")
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause()

        app.action_kill_pane()
        await pilot.pause()

        app._client.kill_pane.assert_not_called()
        assert not isinstance(app.screen, KillPaneModalScreen)


# ============================================================================
# NotifyChannel lifecycle
# ============================================================================


@pytest.mark.asyncio
async def test_app_notifies_config_error():
    """Watcher に config_error があるとき、NotifyChannel にエラーメッセージが送信されること。"""
    app = _patched_app(config_error="invalid regex")
    async with app.run_test() as pilot:
        await pilot.pause(0.1)
        messages = [call.args[0] for call in app._notify_channel.send.call_args_list if call.args]
        assert any("invalid regex" in m for m in messages)


@pytest.mark.asyncio
async def test_notify_channel_started_on_mount():
    """on_mount で NotifyChannel.start() が呼ばれること。"""
    app = _patched_app()
    async with app.run_test():
        app._notify_channel.start.assert_called_once()


@pytest.mark.asyncio
async def test_events_sent_through_notify_channel():
    """リフレッシュ時に NotifyChannel.send() 経由で通知されること。"""
    tree = make_tree()
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        app.query_one("#tmux-tree").focus()
        await pilot.press("r")
        assert any(
            call.args[0] == "Refreshed"
            for call in app._notify_channel.send.call_args_list
            if call.args
        )


# ============================================================================
# Custom labels: applied on refresh
# ============================================================================


@pytest.mark.asyncio
async def test_labels_applied_on_refresh(tmp_path):
    """Custom labels from LabelStore should appear in the tree after refresh."""
    from muxpilot.label_store import LabelStore
    store = LabelStore(config_path=tmp_path / "config.toml")

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    app = _patched_app(tree=tree, label_store=store)
    async with app.run_test() as pilot:
        app._label_store.set("work", "🚀 Main Project")
        await app.action_refresh()
        await pilot.pause()

        tw = app.query_one("#tmux-tree", TmuxTreeView)
        for node_id, (node_type, session, window, pane) in tw._node_data.items():
            if node_type == "session" and session:
                assert session.custom_label == "🚀 Main Project"


# ============================================================================
# Custom labels: rename action (n key)
# ============================================================================


@pytest.mark.asyncio
async def test_rename_key_shows_input(tmp_path):
    """Pressing n should show the rename input."""
    from textual.widgets import Input
    from muxpilot.label_store import LabelStore

    tree = make_tree(sessions=[
        make_session(session_name="work", windows=[
            make_window(window_name="editor", panes=[make_pane(pane_id="%0")])
        ])
    ])
    store = LabelStore(config_path=tmp_path / "config.toml")
    app = _patched_app(tree=tree, label_store=store)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")  # session
        await pilot.press("j")  # window
        await pilot.press("j")  # pane
        await pilot.pause()

        await app.action_rename()
        await pilot.pause()

        ri = app.query_one("#rename-input", Input)
        assert ri.has_class("-active")


@pytest.mark.asyncio
async def test_rename_submit_saves_label(tmp_path):
    """Submitting a name in rename input should save it via LabelStore."""
    from textual.widgets import Input
    from muxpilot.label_store import LabelStore

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    store = LabelStore(config_path=tmp_path / "config.toml")
    app = _patched_app(tree=tree, label_store=store)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause()

        await app.action_rename()
        await pilot.pause()

        ri = app.query_one("#rename-input", Input)
        ri.value = "my test runner"
        await pilot.press("enter")
        await pilot.pause()

        assert store.get("work.0.0") == "my test runner"


@pytest.mark.asyncio
async def test_rename_empty_deletes_label(tmp_path):
    """Submitting empty string should delete the custom label."""
    from textual.widgets import Input
    from muxpilot.label_store import LabelStore

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    store = LabelStore(config_path=tmp_path / "config.toml")
    store.set("work.0.0", "old label")
    app = _patched_app(tree=tree, label_store=store)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause()

        await app.action_rename()
        await pilot.pause()

        ri = app.query_one("#rename-input", Input)
        ri.value = ""
        await pilot.press("enter")
        await pilot.pause()

        assert store.get("work.0.0") == ""


@pytest.mark.asyncio
async def test_rename_escape_cancels(tmp_path):
    """Pressing Escape during rename should cancel without saving."""
    from textual.widgets import Input
    from muxpilot.label_store import LabelStore

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    store = LabelStore(config_path=tmp_path / "config.toml")
    app = _patched_app(tree=tree, label_store=store)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause()

        await app.action_rename()
        await pilot.pause()

        ri = app.query_one("#rename-input", Input)
        ri.value = "should not save"
        await pilot.press("escape")
        await pilot.pause()

        assert store.get("work.0.0") == ""
        assert not ri.has_class("-active")


# ============================================================================
# Polling: error handling and backoff
# ============================================================================


@pytest.mark.asyncio
async def test_poll_tmux_shows_error_on_exception():
    """When watcher.poll raises, notify channel should show error and polling continues."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])
    ])
    app = _patched_app(tree=tree)
    app._watcher.poll = MagicMock(side_effect=RuntimeError("tmux down"))
    async with app.run_test() as pilot:
        app._notify_channel.send.reset_mock()
        await app._poll_tmux()
        messages = [call.args[0] for call in app._notify_channel.send.call_args_list if call.args]
        assert any("tmux down" in m for m in messages)


@pytest.mark.asyncio
async def test_poll_tmux_pauses_timer_on_exception():
    """When watcher.poll raises, the repeating poll timer should be paused."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        app._poll_timer = MagicMock()
        app._watcher.poll = MagicMock(side_effect=RuntimeError("tmux down"))
        with patch.object(app, "set_interval") as mock_set_interval:
            await app._poll_tmux()
        app._poll_timer.pause.assert_called_once()
        mock_set_interval.assert_called_once_with(
            POLL_INTERVAL_SECONDS * 2, app._poll_tmux, repeat=False
        )


@pytest.mark.asyncio
async def test_poll_tmux_backoff_doubles_after_failure():
    """_poll_backoff should double after each failure."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        app._poll_timer = MagicMock()
        app._watcher.poll = MagicMock(side_effect=RuntimeError("tmux down"))
        assert app._poll_backoff == POLL_INTERVAL_SECONDS
        with patch.object(app, "set_interval"):
            await app._poll_tmux()
        assert app._poll_backoff == POLL_INTERVAL_SECONDS * 2
        with patch.object(app, "set_interval"):
            await app._poll_tmux()
        assert app._poll_backoff == POLL_INTERVAL_SECONDS * 4


@pytest.mark.asyncio
async def test_poll_tmux_backoff_caps_at_max():
    """_poll_backoff should not exceed MAX_POLL_BACKOFF_SECONDS."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        app._poll_timer = MagicMock()
        app._watcher.poll = MagicMock(side_effect=RuntimeError("tmux down"))
        # Seed backoff so next doubling would exceed the cap
        app._poll_backoff = MAX_POLL_BACKOFF_SECONDS - 1.0
        with patch.object(app, "set_interval") as mock_set_interval:
            await app._poll_tmux()
        assert app._poll_backoff == MAX_POLL_BACKOFF_SECONDS
        mock_set_interval.assert_called_once_with(
            MAX_POLL_BACKOFF_SECONDS, app._poll_tmux, repeat=False
        )
        # Another failure should stay at the cap
        with patch.object(app, "set_interval") as mock_set_interval:
            await app._poll_tmux()
        assert app._poll_backoff == MAX_POLL_BACKOFF_SECONDS
        mock_set_interval.assert_called_once_with(
            MAX_POLL_BACKOFF_SECONDS, app._poll_tmux, repeat=False
        )


@pytest.mark.asyncio
async def test_poll_tmux_resumes_timer_on_recovery():
    """After a polling failure, success should resume the repeating timer and reset backoff."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        app._poll_timer = MagicMock()
        app._watcher.poll = MagicMock(side_effect=[RuntimeError("tmux down"), (tree, [])])
        with patch.object(app, "set_interval"):
            await app._poll_tmux()
        app._poll_timer.pause.assert_called_once()
        assert app._poll_backoff == POLL_INTERVAL_SECONDS * 2
        await app._poll_tmux()
        app._poll_timer.resume.assert_called_once()
        assert app._poll_backoff == POLL_INTERVAL_SECONDS
