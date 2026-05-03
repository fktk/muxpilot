"""Tests for navigation actions (Enter, cursor preservation)."""

from __future__ import annotations

import pytest

from muxpilot.widgets.tree_view import TmuxTreeView

from _test_app_common import _patched_app
from conftest import make_pane, make_session, make_tree, make_window


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


