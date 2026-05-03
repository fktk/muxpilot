"""Tests for kill pane modal (x key)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from muxpilot.models import PaneStatus
from muxpilot.screens.kill_modal import KillPaneModalScreen
from muxpilot.widgets.tree_view import TmuxTreeView

from _test_app_common import _patched_app
from conftest import make_pane, make_session, make_tree, make_window


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
