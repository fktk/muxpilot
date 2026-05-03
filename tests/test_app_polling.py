"""Tests for polling, backoff, cooldown, and event suppression."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from muxpilot.app import MAX_POLL_BACKOFF_SECONDS
from muxpilot.models import PaneStatus
from muxpilot.watcher import DEFAULT_POLL_INTERVAL
from muxpilot.widgets.tree_view import TmuxTreeView

from _test_app_common import _patched_app
from conftest import make_pane, make_session, make_tree, make_window


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
        app._polling.poll_timer = MagicMock()
        app._watcher.poll = MagicMock(side_effect=RuntimeError("tmux down"))
        mock_set_interval = MagicMock()
        app._polling._set_interval = mock_set_interval
        await app._poll_tmux()
        app._polling.poll_timer.pause.assert_called_once()
        mock_set_interval.assert_called_once_with(
            DEFAULT_POLL_INTERVAL * 2, app._polling._on_tick_wrapper, repeat=False
        )


@pytest.mark.asyncio
async def test_poll_tmux_backoff_doubles_after_failure():
    """_poll_backoff should double after each failure."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        app._polling.poll_timer = MagicMock()
        app._watcher.poll = MagicMock(side_effect=RuntimeError("tmux down"))
        assert app._polling.backoff == DEFAULT_POLL_INTERVAL
        app._polling._set_interval = MagicMock()
        await app._poll_tmux()
        assert app._polling.backoff == DEFAULT_POLL_INTERVAL * 2
        app._polling._set_interval = MagicMock()
        await app._poll_tmux()
        assert app._polling.backoff == DEFAULT_POLL_INTERVAL * 4


@pytest.mark.asyncio
async def test_poll_tmux_backoff_caps_at_max():
    """_poll_backoff should not exceed MAX_POLL_BACKOFF_SECONDS."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        app._polling.poll_timer = MagicMock()
        app._watcher.poll = MagicMock(side_effect=RuntimeError("tmux down"))
        # Seed backoff so next doubling would exceed the cap
        app._polling.backoff = MAX_POLL_BACKOFF_SECONDS - 1.0
        mock_set_interval = MagicMock()
        app._polling._set_interval = mock_set_interval
        await app._poll_tmux()
        assert app._polling.backoff == MAX_POLL_BACKOFF_SECONDS
        mock_set_interval.assert_called_once_with(
            MAX_POLL_BACKOFF_SECONDS, app._polling._on_tick_wrapper, repeat=False
        )
        # Another failure should stay at the cap
        mock_set_interval = MagicMock()
        app._polling._set_interval = mock_set_interval
        await app._poll_tmux()
        assert app._polling.backoff == MAX_POLL_BACKOFF_SECONDS
        mock_set_interval.assert_called_once_with(
            MAX_POLL_BACKOFF_SECONDS, app._polling._on_tick_wrapper, repeat=False
        )


@pytest.mark.asyncio
async def test_poll_tmux_resumes_timer_on_recovery():
    """After a polling failure, success should resume the repeating timer and reset backoff."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        app._polling.poll_timer = MagicMock()
        app._watcher.poll = MagicMock(side_effect=[RuntimeError("tmux down"), (tree, [])])
        with patch.object(app, "set_interval"):
            await app._poll_tmux()
        app._polling.poll_timer.pause.assert_called_once()
        assert app._polling.backoff == DEFAULT_POLL_INTERVAL * 2
        await app._poll_tmux()
        app._polling.poll_timer.resume.assert_called_once()
        assert app._polling.backoff == DEFAULT_POLL_INTERVAL


# ============================================================================
# main() outside-tmux bootstrap
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
        app._polling.poll_timer = MagicMock()
        app._polling.max_consecutive_failures = 3

        for _ in range(3):
            with patch.object(app, "set_interval"):
                await app._poll_tmux()

        app._polling.poll_timer.stop.assert_called_once()
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


