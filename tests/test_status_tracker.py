"""Tests for muxpilot.status_tracker — pane activity lifecycle tracking."""

from __future__ import annotations

import pytest

from muxpilot.status_tracker import StatusTracker
from muxpilot.models import PaneStatus


class TestStatusTracker:
    """Tests for StatusTracker.analyze_pane and cleanup."""

    @pytest.fixture
    def tracker(self):
        return StatusTracker(preview_lines=30)

    def test_first_analysis(self, tracker):
        activity = tracker.analyze_pane("%0", ["hello"], None, 0.0)
        assert activity.pane_id == "%0"
        assert activity.idle_seconds == 0.0
        assert activity.last_content_hash != ""
        assert activity.content_changed is True

    def test_content_unchanged_increments_idle(self, tracker):
        first = tracker.analyze_pane("%0", ["hello"], None, 0.0)
        second = tracker.analyze_pane("%0", ["hello"], first, 2.0)
        assert second.idle_seconds == 2.0
        assert second.content_changed is False

    def test_content_changed_resets_idle(self, tracker):
        first = tracker.analyze_pane("%0", ["hello"], None, 0.0)
        first.idle_seconds = 10.0
        second = tracker.analyze_pane("%0", ["world"], first, 2.0)
        assert second.idle_seconds == 0.0
        assert second.content_changed is True

    def test_recent_lines_truncated(self, tracker):
        activity = tracker.analyze_pane("%0", ["a", "b", "c", "d"], None, 0.0)
        assert activity.recent_lines == ["a", "b", "c", "d"]

    def test_empty_content(self, tracker):
        activity = tracker.analyze_pane("%0", [], None, 0.0)
        assert activity.last_line == ""
        assert activity.recent_lines == []

    def test_cleanup_removed(self, tracker):
        tracker.analyze_pane("%0", ["hello"], None, 0.0)
        tracker.analyze_pane("%1", ["world"], None, 0.0)
        tracker.cleanup_removed({"%0"})
        assert "%0" in tracker.activities
        assert "%1" not in tracker.activities

    def test_status_override_cleared_on_change(self, tracker):
        first = tracker.analyze_pane("%0", ["hello"], None, 0.0)
        first.status_override = PaneStatus.WAITING_INPUT
        second = tracker.analyze_pane("%0", ["world"], first, 0.0)
        assert second.status_override is None

    def test_status_override_preserved_when_unchanged(self, tracker):
        first = tracker.analyze_pane("%0", ["hello"], None, 0.0)
        first.status_override = PaneStatus.WAITING_INPUT
        second = tracker.analyze_pane("%0", ["hello"], first, 1.0)
        assert second.status_override == PaneStatus.WAITING_INPUT

    def test_logs_content_changed(self, tracker, caplog):
        """Should log content hash and content_changed flag."""
        with caplog.at_level("DEBUG", logger="muxpilot.status_tracker"):
            tracker.analyze_pane("%0", ["hello"], None, 0.0)
        assert "%0" in caplog.text
        assert "content_changed=True" in caplog.text
        assert "hash=" in caplog.text

    def test_logs_status_override_cleared(self, tracker, caplog):
        """Should log when status_override is cleared due to content change."""
        first = tracker.analyze_pane("%0", ["hello"], None, 0.0)
        first.status_override = PaneStatus.WAITING_INPUT
        with caplog.at_level("DEBUG", logger="muxpilot.status_tracker"):
            tracker.analyze_pane("%0", ["world"], first, 0.0)
        assert "status_override cleared" in caplog.text
        assert "%0" in caplog.text

    def test_logs_idle_seconds(self, tracker, caplog):
        """Should log idle_seconds calculation."""
        first = tracker.analyze_pane("%0", ["hello"], None, 0.0)
        with caplog.at_level("DEBUG", logger="muxpilot.status_tracker"):
            second = tracker.analyze_pane("%0", ["hello"], first, 2.5)
        assert "idle_seconds=2.5" in caplog.text
        assert "%0" in caplog.text
