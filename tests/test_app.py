"""Tests for the Textual App — integration tests using App.run_test()."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from muxpilot.models import PaneStatus
from muxpilot.app import MuxpilotApp
from muxpilot.widgets.tree_view import TmuxTreeView

from conftest import make_mock_client, make_mock_notify_channel, make_pane, make_session, make_tree, make_window


def _patched_app(tree=None, current_pane_id=None):
    """Create a MuxpilotApp with a mocked TmuxClient/Watcher."""
    mock_client = make_mock_client(tree=tree, current_pane_id=current_pane_id)
    app = MuxpilotApp()
    app._client = mock_client
    from muxpilot.watcher import TmuxWatcher
    app._watcher = TmuxWatcher(mock_client)
    app._notify_channel = make_mock_notify_channel()
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
        app.on_tmux_tree_view_pane_activated(msg)
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
        app.on_tmux_tree_view_pane_activated(msg)
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
