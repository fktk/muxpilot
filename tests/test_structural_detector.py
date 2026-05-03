"""Tests for muxpilot.structural_detector — detecting tree changes."""

from __future__ import annotations

import pytest

from muxpilot.structural_detector import StructuralChangeDetector
from muxpilot.models import TmuxEvent

from conftest import make_pane, make_session, make_tree, make_window


class TestStructuralChangeDetector:
    """Tests for StructuralChangeDetector.detect."""

    @pytest.fixture
    def detector(self):
        return StructuralChangeDetector()

    def test_pane_added(self, detector):
        old = make_tree(sessions=[make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])])
        new = make_tree(sessions=[make_session(windows=[make_window(panes=[make_pane(pane_id="%0"), make_pane(pane_id="%1")])])])
        events = detector.detect(old, new)
        assert any(e.event_type == "pane_added" and e.pane_id == "%1" for e in events)

    def test_pane_removed(self, detector):
        old = make_tree(sessions=[make_session(windows=[make_window(panes=[make_pane(pane_id="%0"), make_pane(pane_id="%1")])])])
        new = make_tree(sessions=[make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])])
        events = detector.detect(old, new)
        assert any(e.event_type == "pane_removed" and e.pane_id == "%1" for e in events)

    def test_session_added(self, detector):
        old = make_tree(sessions=[make_session(session_name="s1")])
        new = make_tree(sessions=[make_session(session_name="s1"), make_session(session_name="s2")])
        events = detector.detect(old, new)
        assert any(e.event_type == "session_added" and e.session_name == "s2" for e in events)

    def test_session_removed(self, detector):
        old = make_tree(sessions=[make_session(session_name="s1"), make_session(session_name="s2")])
        new = make_tree(sessions=[make_session(session_name="s1")])
        events = detector.detect(old, new)
        assert any(e.event_type == "session_removed" and e.session_name == "s2" for e in events)

    def test_no_changes(self, detector):
        tree = make_tree(sessions=[make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])])
        events = detector.detect(tree, tree)
        assert events == []

    def test_simultaneous_add_remove(self, detector):
        old = make_tree(sessions=[make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])])
        new = make_tree(sessions=[make_session(windows=[make_window(panes=[make_pane(pane_id="%1")])])])
        events = detector.detect(old, new)
        types = {e.event_type for e in events}
        assert "pane_added" in types
        assert "pane_removed" in types

    def test_focus_changed(self, detector):
        old = make_tree(sessions=[make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0", is_active=True),
            make_pane(pane_id="%1", is_active=False),
        ])])])
        new = make_tree(sessions=[make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0", is_active=False),
            make_pane(pane_id="%1", is_active=True),
        ])])])
        events = detector.detect(old, new)
        focus_events = [e for e in events if e.event_type == "focus_changed"]
        assert len(focus_events) == 1
        assert focus_events[0].pane_id == "%1"

    def test_no_focus_event_when_unchanged(self, detector):
        tree = make_tree(sessions=[make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0", is_active=True),
            make_pane(pane_id="%1", is_active=False),
        ])])])
        events = detector.detect(tree, tree)
        focus_events = [e for e in events if e.event_type == "focus_changed"]
        assert focus_events == []
