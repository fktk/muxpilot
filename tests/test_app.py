"""Tests for the Textual App — integration tests using App.run_test()."""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from muxpilot.models import PaneStatus
import pathlib

from muxpilot.app import MuxpilotApp, MAX_POLL_BACKOFF_SECONDS, main
from muxpilot.screens.help_screen import HelpScreen
from muxpilot.watcher import DEFAULT_POLL_INTERVAL
from muxpilot.widgets.tree_view import TmuxTreeView

from conftest import make_mock_client, make_mock_notify_channel, make_pane, make_session, make_tree, make_window


def _run_detail_panel(panel):
    """Wrap a DetailPanel in a minimal App and run it in a test context.

    Yields the panel after mount so callers can inspect _markdown_source.
    """
    from textual.app import App
    from textual.app import ComposeResult

    class _TestApp(App):
        def compose(self) -> ComposeResult:
            yield panel

    return _TestApp()


def _patched_app(tree=None, current_pane_id=None, label_store=None, config_error=None, config_path=None):
    """Create a MuxpilotApp with a mocked TmuxClient/Watcher."""
    mock_client = make_mock_client(tree=tree, current_pane_id=current_pane_id)
    app = MuxpilotApp(config_path=config_path)
    app._client = mock_client
    from muxpilot.controllers import RenameController
    app._rename_controller = RenameController(mock_client)
    from muxpilot.watcher import TmuxWatcher
    app._watcher = TmuxWatcher(mock_client, config_path=pathlib.Path("/nonexistent-muxpilot-config"))
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
async def test_detail_panel_shows_pane_title_and_git():
    """Detail panel should display pane title, repo, branch, and idle time."""
    from muxpilot.widgets.detail_panel import DetailPanel
    panel = DetailPanel()
    session = make_session(session_name="dev", windows=[
        make_window(window_name="editor", panes=[
            make_pane(
                pane_id="%0",
                pane_title="agent-a",
                repo_name="proj",
                branch="feat/x",
                idle_seconds=12.0,
                status=PaneStatus.IDLE,
                recent_lines=["line1", "line2"],
            )
        ])
    ])
    window = session.windows[0]
    pane = window.panes[0]
    app = _run_detail_panel(panel)
    async with app.run_test():
        panel.show_pane(pane, window, session)
        text = panel._markdown_source
        assert "agent-a" in text
        assert "proj" in text
        assert "feat/x" in text
        assert "12.0s idle" in text
        assert "line1" in text
        assert "line2" in text


@pytest.mark.asyncio
async def test_detail_panel_error_status_shows_clean_icon():
    """Detail panel should render ERROR status icon cleanly without broken markup."""
    from muxpilot.widgets.detail_panel import DetailPanel
    panel = DetailPanel()
    session = make_session(session_name="dev", windows=[
        make_window(window_name="editor", panes=[
            make_pane(pane_id="%0", status=PaneStatus.ERROR)
        ])
    ])
    window = session.windows[0]
    pane = window.panes[0]
    app = _run_detail_panel(panel)
    async with app.run_test():
        panel.show_pane(pane, window, session)
        text = panel._markdown_source

        # Should NOT contain broken/unclosed markup fragments
        assert "[bold" not in text, f"Broken bold markup found: {text}"
        assert "red]" not in text, f"Broken red markup found: {text}"
        # Should show the bold letter E in Markdown
        assert "**E**" in text, f"Bold E not found in status line: {text}"
        assert "error" in text


@pytest.mark.asyncio
async def test_detail_panel_pane_shows_session_and_window_before_title():
    """Pane details should show Session and Window before Title, and not repeat them after Recent Output."""
    from muxpilot.widgets.detail_panel import DetailPanel
    panel = DetailPanel()
    session = make_session(session_name="my-session", windows=[
        make_window(window_name="my-window", window_index=3, panes=[
            make_pane(pane_id="%0", pane_title="agent-a", recent_lines=["line1"])
        ])
    ])
    window = session.windows[0]
    pane = window.panes[0]
    app = _run_detail_panel(panel)
    async with app.run_test():
        panel.show_pane(pane, window, session)
        text = panel._markdown_source

        pane_section_start = text.find("## Pane")
        recent_output_start = text.find("## Recent Output")
        assert pane_section_start != -1
        assert recent_output_start != -1
        assert pane_section_start < recent_output_start

        session_pos = text.find("- **Session:** my-session")
        window_pos = text.find("- **Window:** my-window (#3)")
        title_pos = text.find("- **Title:** agent-a")

        assert session_pos != -1, "Session info missing"
        assert window_pos != -1, "Window info missing"
        assert title_pos != -1, "Title info missing"

        assert pane_section_start < session_pos < recent_output_start, "Session should be inside Pane section"
        assert pane_section_start < window_pos < recent_output_start, "Window should be inside Pane section"
        assert pane_section_start < title_pos < recent_output_start, "Title should be inside Pane section"

        assert session_pos < window_pos < title_pos, "Order should be Session -> Window -> Title"

        # Ensure Session/Window do not appear after Recent Output
        after_recent = text[recent_output_start:]
        assert "**Session:**" not in after_recent, "Session should not repeat after Recent Output"
        assert "**Window:**" not in after_recent, "Window should not repeat after Recent Output"


@pytest.mark.asyncio
async def test_detail_panel_window_shows_session_first():
    """Window details should show Session before Name."""
    from muxpilot.widgets.detail_panel import DetailPanel
    panel = DetailPanel()
    session = make_session(session_name="my-session", windows=[
        make_window(window_name="my-window", window_index=3, panes=[
            make_pane(pane_id="%0")
        ])
    ])
    window = session.windows[0]
    app = _run_detail_panel(panel)
    async with app.run_test():
        panel.show_window(window, session)
        text = panel._markdown_source

        window_section_start = text.find("## Window")
        session_pos = text.find("- **Session:** my-session")
        name_pos = text.find("- **Name:** my-window")

        assert window_section_start != -1
        assert session_pos != -1, "Session info missing"
        assert name_pos != -1, "Name info missing"

        assert window_section_start < session_pos < name_pos, "Session should appear before Name in Window section"


@pytest.mark.asyncio
async def test_detail_panel_window_does_not_show_pane_count():
    """Window details should not include pane count."""
    from muxpilot.widgets.detail_panel import DetailPanel
    panel = DetailPanel()
    session = make_session(session_name="my-session", windows=[
        make_window(window_name="my-window", window_index=3, panes=[
            make_pane(pane_id="%0"),
            make_pane(pane_id="%1"),
        ])
    ])
    window = session.windows[0]
    app = _run_detail_panel(panel)
    async with app.run_test():
        panel.show_window(window, session)
        text = panel._markdown_source
        assert "**Panes:**" not in text


@pytest.mark.asyncio
async def test_detail_panel_session_does_not_show_counts():
    """Session details should not include window or pane counts."""
    from muxpilot.widgets.detail_panel import DetailPanel
    panel = DetailPanel()
    session = make_session(session_name="my-session", windows=[
        make_window(window_name="w1", window_index=0, panes=[make_pane(pane_id="%0")]),
        make_window(window_name="w2", window_index=1, panes=[make_pane(pane_id="%1"), make_pane(pane_id="%2")]),
    ])
    app = _run_detail_panel(panel)
    async with app.run_test():
        panel.show_session(session)
        text = panel._markdown_source
        assert "**Windows:**" not in text
    assert "**Panes:**" not in text


@pytest.mark.asyncio
async def test_tree_panel_max_width_default():
    """Tree panel max-width should default to 60 when no config is set."""
    from textual.containers import Vertical
    from textual.css.scalar import Scalar

    app = _patched_app(config_path=pathlib.Path("/nonexistent-config-for-test"))
    async with app.run_test():
        tree_panel = app.query_one("#tree-panel", Vertical)
        assert tree_panel.styles.max_width == Scalar.parse("60")


@pytest.mark.asyncio
async def test_tree_panel_max_width_from_config(tmp_path):
    """Tree panel max-width should be read from config.toml."""
    from textual.containers import Vertical
    from textual.css.scalar import Scalar

    config_path = tmp_path / "config.toml"
    config_path.write_text('[ui]\ntree_panel_max_width = 80\n')

    app = _patched_app(config_path=config_path)
    async with app.run_test():
        tree_panel = app.query_one("#tree-panel", Vertical)
        assert tree_panel.styles.max_width == Scalar.parse("80")


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
async def test_enter_on_window_navigates_to_active_pane():
    """Selecting a window node (Enter) should emit PaneActivated for its active pane."""
    from textual.widgets._tree import Tree

    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0", is_active=True),
            make_pane(pane_id="%1"),
        ])])
    ])
    app = _patched_app(tree=tree, current_pane_id="%99")
    async with app.run_test():
        tw = app.query_one("#tmux-tree", TmuxTreeView)

        # Find the window node
        window_node = None
        for node_id, (node_type, session, window, pane) in tw._node_data.items():
            if node_type == "window":
                window_node = tw.get_node_by_id(node_id)
                break

        assert window_node is not None

        # Capture posted messages while still delivering them so Textual's
        # widget lifecycle stays intact.
        posted = []
        original_post = tw.post_message
        def capture_post(msg):
            posted.append(msg)
            return original_post(msg)
        tw.post_message = capture_post

        # Simulate Enter on the window node
        event = Tree.NodeSelected(window_node)
        tw.on_tree_node_selected(event)

        # Verify tree emitted PaneActivated for the active pane
        assert len(posted) == 1
        assert isinstance(posted[0], TmuxTreeView.PaneActivated)
        assert posted[0].pane_id == "%0"


@pytest.mark.asyncio
async def test_enter_on_session_navigates_to_active_pane():
    """Selecting a session node (Enter) should emit PaneActivated for its active window's active pane."""
    from textual.widgets._tree import Tree

    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0", is_active=True),
            make_pane(pane_id="%1"),
        ])])
    ])
    app = _patched_app(tree=tree, current_pane_id="%99")
    async with app.run_test():
        tw = app.query_one("#tmux-tree", TmuxTreeView)

        # Find the session node
        session_node = None
        for node_id, (node_type, session, window, pane) in tw._node_data.items():
            if node_type == "session":
                session_node = tw.get_node_by_id(node_id)
                break

        assert session_node is not None

        # Capture posted messages while still delivering them
        posted = []
        original_post = tw.post_message
        def capture_post(msg):
            posted.append(msg)
            return original_post(msg)
        tw.post_message = capture_post

        # Simulate Enter on the session node
        event = Tree.NodeSelected(session_node)
        tw.on_tree_node_selected(event)

        # Verify tree emitted PaneActivated for the active pane
        assert len(posted) == 1
        assert isinstance(posted[0], TmuxTreeView.PaneActivated)
        assert posted[0].pane_id == "%0"


@pytest.mark.asyncio
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
async def test_help_screen_esc_closes():
    """Pressing Escape while help is open should dismiss the help screen."""
    app = _patched_app()
    async with app.run_test() as pilot:
        app.push_screen(HelpScreen())
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_q_in_help_screen_does_not_quit():
    """Pressing q while help is open should not exit the app."""
    app = _patched_app()
    async with app.run_test() as pilot:
        app.push_screen(HelpScreen())
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("q")
        await pilot.pause()
        # App should still be running and HelpScreen should still be active
        assert isinstance(app.screen, HelpScreen)
        assert app.is_running


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
# Filter: clear all (c) — call action directly
# ============================================================================


@pytest.mark.asyncio
async def test_filter_all_clears():
    """action_filter_all should clear both status and name filters."""
    from textual.widgets import Input
    app = _patched_app()
    async with app.run_test() as pilot:
        # Set some filter state directly
        app._status_filter = {PaneStatus.ERROR}
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
            old_status=PaneStatus.WAITING_INPUT,
            new_status=PaneStatus.ACTIVE,
            message="%0: waiting → active",
        )
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
async def test_structural_events_not_notified():
    """Structural events (pane_added, etc.) should NOT be sent to NotifyChannel."""
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

        # Verify the structural event was NOT notified
        messages = [call.args[0] for call in app._notify_channel.send.call_args_list if call.args]
        assert "Pane added: %1" not in messages


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
async def test_notification_waiting_trigger_updates_ui():
    """A FIFO message matching waiting_trigger_pattern should refresh the tree."""
    from muxpilot.models import PaneStatus
    import re

    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0", status=PaneStatus.ACTIVE),
        ])])
    ])
    app = _patched_app(tree=tree)
    # Seed the watcher with an activity
    app._watcher.poll()
    app._watcher.waiting_trigger_pattern = re.compile("WAITING")

    async with app.run_test() as pilot:
        app._notify_channel.receive = MagicMock(side_effect=["%0 WAITING", None])

        await app._check_notifications()
        await pilot.pause()

        # The watcher should have updated the pane status
        assert app._watcher.activities["%0"].status == PaneStatus.WAITING_INPUT


@pytest.mark.asyncio
async def test_notification_no_match_shows_raw_toast():
    """A FIFO message that does not match should display as a normal toast."""
    import re
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])
    ])
    app = _patched_app(tree=tree)
    app._watcher.waiting_trigger_pattern = re.compile("WAITING")

    async with app.run_test() as pilot:
        app._notify_channel.receive = MagicMock(side_effect=["hello world", None])

        # Mock app.notify to verify it's called with the raw message
        original_notify = app.notify
        app.notify = MagicMock()

        await app._check_notifications()
        await pilot.pause()

        app.notify.assert_called_once_with("hello world", timeout=5)

        # Restore original notify
        app.notify = original_notify


# ============================================================================
# Custom labels: applied on refresh
# ============================================================================


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
async def test_rename_submit_sets_pane_title():
    """Submitting a name in rename input should call set_pane_title on the client."""
    from textual.widgets import Input

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    app = _patched_app(tree=tree)
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

        app._client.set_pane_title.assert_called_with("%0", "my test runner")


@pytest.mark.asyncio
async def test_rename_empty_sets_empty_pane_title():
    """Submitting empty string should call set_pane_title with empty string."""
    from textual.widgets import Input

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    app = _patched_app(tree=tree)
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

        app._client.set_pane_title.assert_called_with("%0", "")


@pytest.mark.asyncio
async def test_rename_escape_cancels():
    """Pressing Escape during rename should cancel without calling set_pane_title."""
    from textual.widgets import Input

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    app = _patched_app(tree=tree)
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

        app._client.set_pane_title.assert_not_called()
        assert not ri.has_class("-active")


@pytest.mark.asyncio
async def test_detail_panel_updates_on_refresh_without_cursor_change():
    """After _do_refresh, DetailPanel should update even when the selected node hasn't changed."""
    from muxpilot.widgets.detail_panel import DetailPanel

    tree = make_tree(sessions=[
        make_session(session_name="dev", windows=[
            make_window(window_name="editor", panes=[
                make_pane(pane_id="%0", is_active=False)
            ])
        ])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause()

        detail = app.query_one("#detail-panel", DetailPanel)
        initial_text = detail._markdown_source
        # Default mock capture content is shown after mount
        assert "user@host:~$" in initial_text

        # Change the captured pane content and refresh without moving cursor
        app._client.capture_pane_content.return_value = ["new output line"]
        await app._do_refresh()
        # Wait for call_after_refresh to fire after tree repopulates
        await pilot.pause()
        await pilot.pause()

        assert "new output line" in detail._markdown_source
        assert "user@host:~$" not in detail._markdown_source


@pytest.mark.asyncio
async def test_detail_panel_updates_on_poll_without_events():
    """Periodic poll without status events must still refresh DetailPanel."""
    from unittest.mock import patch
    from muxpilot.widgets.detail_panel import DetailPanel

    tree = make_tree(sessions=[
        make_session(session_name="dev", windows=[
            make_window(window_name="editor", panes=[
                make_pane(pane_id="%0", is_active=False, status=PaneStatus.ACTIVE)
            ])
        ])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause()

        detail = app.query_one("#detail-panel", DetailPanel)
        assert "user@host:~$" in detail._markdown_source

        # Build a new tree with updated recent_lines but no events
        updated_tree = make_tree(sessions=[
            make_session(session_name="dev", windows=[
                make_window(window_name="editor", panes=[
                    make_pane(
                        pane_id="%0",
                        is_active=False,
                        status=PaneStatus.ACTIVE,
                        recent_lines=["polled output"],
                    )
                ])
            ])
        ])
        # Patch watcher.poll to return updated tree with no events
        with patch.object(app._watcher, "poll", return_value=(updated_tree, [])):
            await app._poll_tmux()
            await pilot.pause()
            await pilot.pause()

        assert "polled output" in detail._markdown_source
        assert "user@host:~$" not in detail._markdown_source


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
async def test_poll_tmux_suppresses_error_when_notify_disabled():
    """When notify_poll_errors is False, poll errors should not be sent to notify channel."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])
    ])
    app = _patched_app(tree=tree)
    app._watcher.notify_poll_errors = False
    async with app.run_test() as pilot:
        app._notify_channel.send.reset_mock()
        app._watcher.poll = MagicMock(side_effect=RuntimeError("tmux down"))
        await app._poll_tmux()
        messages = [call.args[0] for call in app._notify_channel.send.call_args_list if call.args]
        assert not any("tmux down" in m for m in messages)


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
            DEFAULT_POLL_INTERVAL * 2, app._poll_tmux, repeat=False
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
        assert app._poll_backoff == DEFAULT_POLL_INTERVAL
        with patch.object(app, "set_interval"):
            await app._poll_tmux()
        assert app._poll_backoff == DEFAULT_POLL_INTERVAL * 2
        with patch.object(app, "set_interval"):
            await app._poll_tmux()
        assert app._poll_backoff == DEFAULT_POLL_INTERVAL * 4


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
        assert app._poll_backoff == DEFAULT_POLL_INTERVAL * 2
        await app._poll_tmux()
        app._poll_timer.resume.assert_called_once()
        assert app._poll_backoff == DEFAULT_POLL_INTERVAL


# ============================================================================
# main() outside-tmux bootstrap
# ============================================================================


@patch("muxpilot.app.os.execlp")
@patch("muxpilot.app.subprocess.run")
@patch("muxpilot.app.TmuxClient")
def test_main_outside_tmux_creates_session_and_attaches(mock_client_cls, mock_run, mock_execlp):
    """When started outside tmux, main() should create a new session and attach."""
    mock_client = MagicMock()
    mock_client.is_inside_tmux.return_value = False
    mock_client_cls.return_value = mock_client

    # os.execlp should replace the process — mock it to raise so we can verify
    mock_execlp.side_effect = SystemExit(0)

    with pytest.raises(SystemExit):
        main()

    mock_run.assert_called_once_with(
        ["tmux", "new-session", "-s", "muxpilot", "-d", sys.executable, "-m", "muxpilot"],
        check=True,
    )
    mock_execlp.assert_called_once_with(
        "tmux", "tmux", "attach", "-t", "muxpilot"
    )


@patch("muxpilot.app.os.execlp")
@patch("muxpilot.app.subprocess.run")
@patch("muxpilot.app.TmuxClient")
@patch("muxpilot.app.MuxpilotApp")
def test_main_inside_tmux_runs_app(mock_app_cls, mock_client_cls, mock_run, mock_execlp):
    """When started inside tmux, main() should run MuxpilotApp normally."""
    mock_client = MagicMock()
    mock_client.is_inside_tmux.return_value = True
    mock_client_cls.return_value = mock_client

    mock_app = MagicMock()
    mock_app.run.return_value = None
    mock_app_cls.return_value = mock_app

    main()

    mock_run.assert_not_called()
    mock_execlp.assert_not_called()
    mock_app.run.assert_called_once()


@patch("muxpilot.app.os.execlp")
@patch("muxpilot.app.subprocess.run")
@patch("muxpilot.app.TmuxClient")
def test_main_outside_tmux_attaches_even_if_session_exists(mock_client_cls, mock_run, mock_execlp):
    """If new-session fails (session already exists), main() should still try to attach."""
    mock_client = MagicMock()
    mock_client.is_inside_tmux.return_value = False
    mock_client_cls.return_value = mock_client

    mock_run.side_effect = subprocess.CalledProcessError(1, "tmux")
    mock_execlp.side_effect = SystemExit(0)

    with pytest.raises(SystemExit):
        main()

    mock_run.assert_called_once()
    mock_execlp.assert_called_once_with(
        "tmux", "tmux", "attach", "-t", "muxpilot"
    )


# ============================================================================
# Polling cooldown
# ============================================================================


@pytest.mark.asyncio
async def test_poll_cooldown_skips_tick():
    """When cooldown is active, tick() should return None without polling."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test():
        app._polling.trigger_cooldown(60.0)
        result = await app._polling.tick()
        assert result is None


@pytest.mark.asyncio
async def test_poll_retry_limit_stops_polling():
    """After max_consecutive_failures, polling should stop and notify."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        app._watcher.poll = MagicMock(side_effect=RuntimeError("tmux down"))
        app._poll_timer = MagicMock()
        app._polling.max_consecutive_failures = 3

        for _ in range(3):
            with patch.object(app, "set_interval"):
                await app._poll_tmux()

        app._poll_timer.stop.assert_called_once()
        messages = [call.args[0] for call in app._notify_channel.send.call_args_list if call.args]
        assert any("stopped after 3 consecutive failures" in m for m in messages)


# ============================================================================
# Cooldown triggered by user actions
# ============================================================================


@pytest.mark.asyncio
async def test_navigate_triggers_cooldown():
    """Navigating to a pane should trigger polling cooldown."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0", is_active=False)])])
    ])
    app = _patched_app(tree=tree, current_pane_id="%99")
    async with app.run_test():
        app._polling.trigger_cooldown = MagicMock()
        msg = TmuxTreeView.PaneActivated(pane_id="%0")
        await app.on_tmux_tree_view_pane_activated(msg)
        app._polling.trigger_cooldown.assert_called_once()


@pytest.mark.asyncio
async def test_kill_triggers_cooldown():
    """Killing a pane should trigger polling cooldown."""
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

        app._polling.trigger_cooldown = MagicMock()
        await pilot.press("y")
        await pilot.pause()

        app._polling.trigger_cooldown.assert_called_once()
