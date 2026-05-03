"""Tests for FIFO notification processing."""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest

from muxpilot.models import PaneStatus

from _test_app_common import _patched_app
from conftest import make_pane, make_session, make_tree, make_window


@pytest.mark.asyncio
async def test_notification_waiting_trigger_updates_ui():
    """A FIFO message matching waiting_trigger_pattern should refresh the tree."""
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

        with patch.object(app, "notify") as mock_notify:
            app._check_notifications()
            await pilot.pause()

            # The watcher should have updated the pane status
            assert app._watcher.activities["%0"].status == PaneStatus.WAITING_INPUT
            mock_notify.assert_called_once_with("%0 → waiting", timeout=3)


@pytest.mark.asyncio
async def test_notification_no_match_shows_raw_toast():
    """A FIFO message that does not match should display as a normal toast."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])
    ])
    app = _patched_app(tree=tree)
    app._watcher.waiting_trigger_pattern = re.compile("WAITING")

    async with app.run_test() as pilot:
        app._notify_channel.receive = MagicMock(side_effect=["hello world", None])

        with patch.object(app, "notify") as mock_notify:
            app._check_notifications()
            await pilot.pause()

            mock_notify.assert_called_once_with("hello world", timeout=5)


@pytest.mark.asyncio
async def test_notification_waiting_trigger_before_first_poll():
    """A notification before first poll should update activity but not crash."""
    import re

    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0", status=PaneStatus.ACTIVE),
        ])])
    ])
    app = _patched_app(tree=tree)
    app._watcher.poll()  # seed activities
    app._watcher._last_tree = None  # simulate no poll yet
    app._watcher.waiting_trigger_pattern = re.compile("WAITING")

    async with app.run_test() as pilot:
        app._notify_channel.receive = MagicMock(side_effect=["%0 WAITING", None])
        with patch.object(app, "notify") as mock_notify:
            app._check_notifications()
            await pilot.pause()
            # Should not crash; activity updated
            assert app._watcher.activities["%0"].status == PaneStatus.WAITING_INPUT
            # Toast should still be shown
            mock_notify.assert_called_once_with("%0 → waiting", timeout=3)


# ============================================================================
# Custom labels: applied on refresh
# ============================================================================


# ============================================================================
# Custom labels: rename action (n key)
# ============================================================================


