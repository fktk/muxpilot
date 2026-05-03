"""Tests for muxpilot.watcher — pattern detection and structural change detection."""

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


class TestDetermineStatus:
    """Tests for _determine_status — the core pattern detection logic."""

    def _status(self, content, last_line="", idle=0.0, threshold=10.0, old_status=None, content_changed=True):
        w = _make_watcher(idle_threshold=threshold)
        old_status = old_status if old_status is not None else PaneStatus.ACTIVE
        return w._determine_status(content, last_line, idle, old_status, content_changed)

    def test_active_when_content_changing(self):
        assert self._status(["output"], "output", idle=0.0) == PaneStatus.ACTIVE

    def test_idle_when_no_change(self):
        assert self._status(["output"], "output", idle=15.0, old_status=PaneStatus.ACTIVE, content_changed=False) == PaneStatus.IDLE

    def test_idle_threshold_not_met_stays_active(self):
        assert self._status(["output"], "output", idle=5.0, old_status=PaneStatus.ACTIVE, content_changed=False) == PaneStatus.ACTIVE

    def test_completed_shell_prompt(self):
        assert self._status(["user@host:~$ "], "user@host:~$ ", idle=0.0) == PaneStatus.WAITING_INPUT

    def test_waiting_shell_prompt(self):
        assert self._status(["user@host:~$ "], "user@host:~$ ", idle=15.0) == PaneStatus.WAITING_INPUT

    def test_waiting_python_repl(self):
        assert self._status([">>> "], ">>> ", idle=15.0) == PaneStatus.WAITING_INPUT

    def test_waiting_ipython(self):
        assert self._status(["In [1]: "], "In [1]: ", idle=15.0) == PaneStatus.WAITING_INPUT

    def test_waiting_yes_no(self):
        assert self._status(["Continue? (y/n) "], "Continue? (y/n) ", idle=15.0) == PaneStatus.WAITING_INPUT

    def test_error_traceback(self):
        lines = ["some code", "Traceback (most recent call last)", "  File ..."]
        assert self._status(lines, "  File ...", idle=0.0) == PaneStatus.ERROR

    def test_error_exception(self):
        lines = ["ValueError: invalid literal"]
        assert self._status(lines, lines[-1], idle=0.0) == PaneStatus.ERROR

    def test_error_failed(self):
        lines = ["FAILED: test_xyz"]
        assert self._status(lines, lines[-1], idle=0.0) == PaneStatus.ERROR

    def test_error_panic(self):
        lines = ["panic: runtime error"]
        assert self._status(lines, lines[-1], idle=0.0) == PaneStatus.ERROR

    def test_error_segfault(self):
        lines = ["Segmentation fault"]
        assert self._status(lines, lines[-1], idle=0.0) == PaneStatus.ERROR

    def test_error_fatal(self):
        lines = ["FATAL: cannot start"]
        assert self._status(lines, lines[-1], idle=0.0) == PaneStatus.ERROR

    def test_error_takes_priority_over_prompt(self):
        """When both error and prompt are present, ERROR should win."""
        lines = ["Error: something failed", "user@host:~$ "]
        assert self._status(lines, "user@host:~$ ", idle=15.0) == PaneStatus.ERROR

    def test_error_persists_when_no_change(self):
        """ERROR status should persist until content changes."""
        assert self._status(["Error: old"], "Error: old", idle=60.0, old_status=PaneStatus.ERROR, content_changed=False) == PaneStatus.ERROR

    def test_waiting_persists_when_no_change(self):
        """WAITING_INPUT status should persist until content changes."""
        assert self._status(["$ "], "$ ", idle=60.0, old_status=PaneStatus.WAITING_INPUT, content_changed=False) == PaneStatus.WAITING_INPUT

    def test_error_resets_on_change_without_pattern(self):
        """ERROR should reset to ACTIVE when content changes and no error pattern matches."""
        assert self._status(["normal output"], "normal output", idle=0.0, old_status=PaneStatus.ERROR, content_changed=True) == PaneStatus.ACTIVE

    def test_waiting_resets_on_change_without_pattern(self):
        """WAITING_INPUT should reset to ACTIVE when content changes and no prompt matches."""
        assert self._status(["normal output"], "normal output", idle=0.0, old_status=PaneStatus.WAITING_INPUT, content_changed=True) == PaneStatus.ACTIVE

    def test_empty_content(self):
        assert self._status([], "", idle=0.0) == PaneStatus.ACTIVE

    def test_only_whitespace_lines(self):
        lines = ["   ", "  ", ""]
        assert self._status(lines, "", idle=0.0) == PaneStatus.ACTIVE


class TestDetectStructuralChanges:
    """Tests for _detect_structural_changes."""

    def test_pane_added(self):
        old = make_tree(sessions=[make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])])
        new = make_tree(sessions=[make_session(windows=[make_window(panes=[make_pane(pane_id="%0"), make_pane(pane_id="%1")])])])
        w = _make_watcher()
        events = w._detect_structural_changes(old, new)
        assert any(e.event_type == "pane_added" and e.pane_id == "%1" for e in events)

    def test_pane_removed(self):
        old = make_tree(sessions=[make_session(windows=[make_window(panes=[make_pane(pane_id="%0"), make_pane(pane_id="%1")])])])
        new = make_tree(sessions=[make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])])
        w = _make_watcher()
        events = w._detect_structural_changes(old, new)
        assert any(e.event_type == "pane_removed" and e.pane_id == "%1" for e in events)

    def test_session_added(self):
        old = make_tree(sessions=[make_session(session_name="s1")])
        new = make_tree(sessions=[make_session(session_name="s1"), make_session(session_name="s2")])
        w = _make_watcher()
        events = w._detect_structural_changes(old, new)
        assert any(e.event_type == "session_added" and e.session_name == "s2" for e in events)

    def test_session_removed(self):
        old = make_tree(sessions=[make_session(session_name="s1"), make_session(session_name="s2")])
        new = make_tree(sessions=[make_session(session_name="s1")])
        w = _make_watcher()
        events = w._detect_structural_changes(old, new)
        assert any(e.event_type == "session_removed" and e.session_name == "s2" for e in events)

    def test_no_changes(self):
        tree = make_tree(sessions=[make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])])
        w = _make_watcher()
        events = w._detect_structural_changes(tree, tree)
        assert events == []

    def test_simultaneous_add_remove(self):
        old = make_tree(sessions=[make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])])
        new = make_tree(sessions=[make_session(windows=[make_window(panes=[make_pane(pane_id="%1")])])])
        w = _make_watcher()
        events = w._detect_structural_changes(old, new)
        types = {e.event_type for e in events}
        assert "pane_added" in types
        assert "pane_removed" in types


class TestAnalyzePane:
    """Tests for _analyze_pane."""

    def test_first_analysis(self):
        w = _make_watcher()
        w._last_tree = make_tree(timestamp=100.0)
        activity = w._analyze_pane("%0", ["hello"], None, 0.0)
        assert activity.pane_id == "%0"
        assert activity.idle_seconds == 0.0
        assert activity.last_content_hash != ""
        assert activity.content_changed is True

    def test_content_unchanged_increments_idle(self):
        w = _make_watcher()
        w._last_tree = make_tree(timestamp=100.0)
        first = w._analyze_pane("%0", ["hello"], None, 0.0)
        w._last_tree = make_tree(timestamp=100.0)
        second = w._analyze_pane("%0", ["hello"], first, 2.0)
        assert second.idle_seconds == 2.0
        assert second.content_changed is False

    def test_content_changed_resets_idle(self):
        w = _make_watcher()
        w._last_tree = make_tree(timestamp=100.0)
        first = w._analyze_pane("%0", ["hello"], None, 0.0)
        first.idle_seconds = 10.0
        w._last_tree = make_tree(timestamp=100.0)
        second = w._analyze_pane("%0", ["world"], first, 2.0)
        assert second.idle_seconds == 0.0
        assert second.content_changed is True


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
