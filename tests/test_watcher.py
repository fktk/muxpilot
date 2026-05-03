"""Integration tests for muxpilot.watcher — TmuxWatcher end-to-end behavior."""

from __future__ import annotations

import pathlib
import re

import pytest

from muxpilot.models import PaneActivity, PaneStatus, TmuxTree
from muxpilot.watcher import TmuxWatcher

from conftest import make_mock_client, make_pane, make_session, make_tree, make_window


def _make_watcher(
    tree=None, capture=None, current_pane_id=None, idle_threshold=10.0, config_path=pathlib.Path("/nonexistent-muxpilot-config")
):
    client = make_mock_client(
        tree=tree, capture_content=capture, current_pane_id=current_pane_id
    )
    return TmuxWatcher(client, idle_threshold=idle_threshold, config_path=config_path)


class TestPoll:
    """Tests for the poll method (integration)."""

    def test_first_call_no_structural_events(self):
        w = _make_watcher()
        _, events = w.poll()
        structural = [e for e in events if e.event_type in ("pane_added", "pane_removed", "session_added", "session_removed")]
        assert structural == []

    def test_status_change_event(self):
        tree = make_tree(sessions=[make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])])
        client = make_mock_client(tree=tree, capture_content=["user@host:~$ "])
        w = TmuxWatcher(client, idle_threshold=10.0)

        w.poll()  # first poll — sets initial status

        # Simulate content change to error
        client.capture_pane_content.return_value = ["Error: something broke"]
        _, events = w.poll()
        status_events = [e for e in events if e.event_type == "status_changed"]
        assert len(status_events) > 0

    def test_cleans_up_removed_panes(self):
        tree1 = make_tree(sessions=[make_session(windows=[make_window(panes=[make_pane(pane_id="%0"), make_pane(pane_id="%1")])])])
        tree2 = make_tree(sessions=[make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])])
        client = make_mock_client(tree=tree1)
        w = TmuxWatcher(client)
        w.poll()
        assert "%1" in w.activities

        client.get_tree.return_value = tree2
        w.poll()
        assert "%1" not in w.activities

    def test_skips_self_pane(self):
        tree = make_tree(sessions=[make_session(windows=[make_window(panes=[make_pane(pane_id="%5")])])])
        client = make_mock_client(tree=tree, current_pane_id="%5")
        w = TmuxWatcher(client)
        new_tree, _ = w.poll()
        self_pane = [p for p in new_tree.all_panes() if p.pane_id == "%5"][0]
        assert self_pane.status == PaneStatus.ACTIVE
        client.capture_pane_content.assert_not_called()

    def test_active_pane_change_emits_event(self):
        """Switching the active pane in tmux should emit a focus_changed event."""
        tree1 = make_tree(sessions=[make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0", is_active=True),
            make_pane(pane_id="%1", is_active=False),
        ])])])
        tree2 = make_tree(sessions=[make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0", is_active=False),
            make_pane(pane_id="%1", is_active=True),
        ])])])
        client = make_mock_client(tree=tree1)
        w = TmuxWatcher(client)
        w.poll()  # first poll

        client.get_tree.return_value = tree2
        _, events = w.poll()
        focus_events = [e for e in events if e.event_type == "focus_changed"]
        assert len(focus_events) == 1
        assert focus_events[0].pane_id == "%1"

    def test_no_focus_event_when_active_pane_unchanged(self):
        """No focus_changed event when the active pane stays the same."""
        tree = make_tree(sessions=[make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0", is_active=True),
            make_pane(pane_id="%1", is_active=False),
        ])])])
        client = make_mock_client(tree=tree)
        w = TmuxWatcher(client)
        w.poll()

        _, events = w.poll()
        focus_events = [e for e in events if e.event_type == "focus_changed"]
        assert focus_events == []

    def test_poll_sets_recent_lines_on_activity(self):
        client = make_mock_client(capture_content=["line1", "line2", "line3"])
        w = TmuxWatcher(client, preview_lines=2)
        tree, _ = w.poll()
        activity = w.activities.get(tree.all_panes()[0].pane_id)
        assert activity is not None
        assert activity.recent_lines == ["line2", "line3"]

    def test_poll_sets_idle_seconds_on_pane_info(self):
        tree = make_tree(sessions=[make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])])
        client = make_mock_client(tree=tree, capture_content=["$ "])
        w = TmuxWatcher(client)
        tree, _ = w.poll()
        assert tree.all_panes()[0].idle_seconds == 0.0


class TestProcessNotification:
    """Tests for process_notification — toast-triggered status changes."""

    def _watcher_with_pattern(self, pattern="WAITING"):
        tree = make_tree(sessions=[
            make_session(windows=[make_window(panes=[
                make_pane(pane_id="%0", status=PaneStatus.ACTIVE),
                make_pane(pane_id="%1", status=PaneStatus.ERROR),
            ])])
        ])
        client = make_mock_client(tree=tree, capture_content=["normal output"])
        watcher = TmuxWatcher(client, config_path=pathlib.Path("/nonexistent"))
        watcher.waiting_trigger_pattern = re.compile(pattern)
        # Seed activities so panes are known; poll() leaves them ACTIVE due to capture_content
        watcher.poll()
        # Manually set %1 to ERROR for the error transition test
        watcher.activities["%1"].status = PaneStatus.ERROR
        return watcher

    def test_matching_message_returns_event_and_updates_status(self):
        w = self._watcher_with_pattern()
        event = w.process_notification("Task complete %0 WAITING")
        assert event is not None
        assert event.event_type == "status_changed"
        assert event.pane_id == "%0"
        assert event.new_status == PaneStatus.WAITING_INPUT
        assert w.activities["%0"].status == PaneStatus.WAITING_INPUT

    def test_matching_message_without_pane_id_returns_none(self):
        w = self._watcher_with_pattern()
        event = w.process_notification("Just WAITING here")
        assert event is None

    def test_message_with_pane_id_but_no_pattern_match_returns_none(self):
        w = self._watcher_with_pattern()
        event = w.process_notification("%0 is done")
        assert event is None

    def test_unknown_pane_returns_none(self):
        w = self._watcher_with_pattern()
        event = w.process_notification("%99 WAITING")
        assert event is None

    def test_disabled_pattern_returns_none(self):
        w = self._watcher_with_pattern()
        w.waiting_trigger_pattern = None
        event = w.process_notification("%0 WAITING")
        assert event is None

    def test_regex_pattern_match(self):
        w = self._watcher_with_pattern(pattern="(?i)waiting|ready")
        event = w.process_notification("%0 ready for input")
        assert event is not None
        assert event.new_status == PaneStatus.WAITING_INPUT

    def test_already_waiting_returns_event(self):
        """Even if pane is already WAITING_INPUT, return event for UI feedback."""
        w = self._watcher_with_pattern()
        w.activities["%0"].status = PaneStatus.WAITING_INPUT
        event = w.process_notification("%0 WAITING")
        assert event is not None
        assert event.new_status == PaneStatus.WAITING_INPUT

    def test_error_to_waiting_transition(self):
        w = self._watcher_with_pattern()
        event = w.process_notification("%1 WAITING")
        assert event is not None
        assert event.old_status == PaneStatus.ERROR
        assert event.new_status == PaneStatus.WAITING_INPUT
        assert w.activities["%1"].status == PaneStatus.WAITING_INPUT

    def test_status_override_set_by_notification(self):
        """process_notification should set status_override on the activity."""
        w = self._watcher_with_pattern()
        w.process_notification("%0 WAITING")
        assert w.activities["%0"].status_override == PaneStatus.WAITING_INPUT

    def test_status_override_persists_across_polls_when_content_unchanged(self):
        """If content hasn't changed, status_override should keep the pane WAITING across polls."""
        w = self._watcher_with_pattern()
        w.process_notification("%0 WAITING")
        assert w.activities["%0"].status == PaneStatus.WAITING_INPUT

        # Poll again with unchanged content — status_override should keep it WAITING
        w.poll()
        assert w.activities["%0"].status == PaneStatus.WAITING_INPUT

    def test_status_override_cleared_when_content_changes(self):
        """status_override should be cleared when pane content changes."""
        w = self._watcher_with_pattern()
        w.process_notification("%0 WAITING")
        assert w.activities["%0"].status_override == PaneStatus.WAITING_INPUT

        # Change pane content so it doesn't match any prompt pattern
        w.client.capture_pane_content.return_value = ["new output line"]
        w.poll()

        # status_override should be cleared, and status should go back to ACTIVE
        assert w.activities["%0"].status_override is None
        assert w.activities["%0"].status == PaneStatus.ACTIVE

    def test_status_override_preserved_when_prompt_pattern_matches(self):
        """Even if content changes, if prompt pattern matches, status should stay WAITING."""
        w = self._watcher_with_pattern()
        w.process_notification("%0 WAITING")
        assert w.activities["%0"].status_override == PaneStatus.WAITING_INPUT

        # Change content to a prompt pattern
        w.client.capture_pane_content.return_value = ["user@host:~$ "]
        w.poll()

        # status_override is cleared because content changed, but prompt pattern keeps it WAITING
        assert w.activities["%0"].status is PaneStatus.WAITING_INPUT
