"""Tests for muxpilot.models — data models and display labels."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from muxpilot.models import (
    PaneInfo,
    PaneStatus,
    STATUS_ICONS,
    SessionInfo,
    TmuxTree,
    WindowInfo,
    _shorten_path,
)

from conftest import make_pane, make_session, make_tree, make_window


# ============================================================================
# PaneInfo.display_label
# ============================================================================


class TestPaneInfoDisplayLabel:
    """Tests for PaneInfo.display_label property."""

    @pytest.mark.parametrize(
        "status",
        list(PaneStatus),
        ids=[s.name for s in PaneStatus],
    )
    def test_display_label_with_status(self, status: PaneStatus) -> None:
        """Each PaneStatus should produce the correct icon in the label."""
        pane = make_pane(
            pane_id="%5",
            current_command="vim",
            current_path="/tmp",
            status=status,
        )
        expected_icon = STATUS_ICONS[status]
        assert pane.display_label.startswith(expected_icon)
        assert "%5" in pane.display_label
        assert "[vim]" in pane.display_label

    def test_display_label_path_shortening(self) -> None:
        """Home directory should be shortened to ~."""
        home = os.path.expanduser("~")
        pane = make_pane(current_path=f"{home}/projects/foo")
        assert "~/projects/foo" in pane.display_label

    def test_display_label_non_home_path(self) -> None:
        """Paths outside home should not be shortened."""
        pane = make_pane(current_path="/tmp/work")
        assert "/tmp/work" in pane.display_label

    def test_display_label_empty_path(self) -> None:
        """Empty path should not cause errors."""
        pane = make_pane(current_path="")
        label = pane.display_label
        assert "[]" not in label  # command brackets still present
        assert pane.pane_id in label

    def test_display_label_empty_command(self) -> None:
        """Empty command should produce empty brackets."""
        pane = make_pane(current_command="")
        assert "[]" in pane.display_label


# ============================================================================
# WindowInfo.display_label
# ============================================================================


class TestWindowInfoDisplayLabel:
    """Tests for WindowInfo.display_label property."""

    def test_display_label_active(self) -> None:
        """Active window should show ' *' suffix."""
        window = make_window(window_name="editor", window_index=1, is_active=True)
        assert "editor" in window.display_label
        assert "*" in window.display_label

    def test_display_label_inactive(self) -> None:
        """Inactive window should not show '*'."""
        window = make_window(window_name="logs", window_index=2, is_active=False)
        assert "logs" in window.display_label
        assert "*" not in window.display_label


# ============================================================================
# SessionInfo.display_label
# ============================================================================


class TestSessionInfoDisplayLabel:
    """Tests for SessionInfo.display_label property."""

    def test_display_label_attached(self) -> None:
        """Attached session should show '(attached)'."""
        session = make_session(session_name="work", is_attached=True)
        assert "work" in session.display_label
        assert "(attached)" in session.display_label

    def test_display_label_detached(self) -> None:
        """Detached session should not show '(attached)'."""
        session = make_session(session_name="work", is_attached=False)
        assert "work" in session.display_label
        assert "(attached)" not in session.display_label


# ============================================================================
# TmuxTree
# ============================================================================


class TestTmuxTree:
    """Tests for TmuxTree properties and methods."""

    def test_total_sessions(self) -> None:
        tree = make_tree(sessions=[make_session(session_id="$0"), make_session(session_id="$1")])
        assert tree.total_sessions == 2

    def test_total_windows(self) -> None:
        """Total windows should sum across all sessions."""
        s1 = make_session(
            session_id="$0",
            windows=[
                make_window(window_id="@0"),
                make_window(window_id="@1"),
            ],
        )
        s2 = make_session(session_id="$1", windows=[make_window(window_id="@2")])
        tree = make_tree(sessions=[s1, s2])
        assert tree.total_windows == 3

    def test_total_panes(self) -> None:
        """Total panes should sum across all windows and sessions."""
        w1 = make_window(
            window_id="@0",
            panes=[make_pane(pane_id="%0"), make_pane(pane_id="%1")],
        )
        w2 = make_window(window_id="@1", panes=[make_pane(pane_id="%2")])
        s = make_session(windows=[w1, w2])
        tree = make_tree(sessions=[s])
        assert tree.total_panes == 3

    def test_all_panes(self) -> None:
        """all_panes should flatten across all sessions/windows."""
        w1 = make_window(
            window_id="@0",
            panes=[make_pane(pane_id="%0"), make_pane(pane_id="%1")],
        )
        w2 = make_window(window_id="@1", panes=[make_pane(pane_id="%2")])
        s = make_session(windows=[w1, w2])
        tree = make_tree(sessions=[s])
        pane_ids = [p.pane_id for p in tree.all_panes()]
        assert pane_ids == ["%0", "%1", "%2"]

    def test_empty_tree(self) -> None:
        """Empty tree should have all zeros and empty pane list."""
        tree = TmuxTree(sessions=[])
        assert tree.total_sessions == 0
        assert tree.total_windows == 0
        assert tree.total_panes == 0
        assert tree.all_panes() == []


# ============================================================================
# _shorten_path
# ============================================================================


class TestShortenPath:
    """Tests for the _shorten_path helper."""

    def test_shorten_home(self) -> None:
        home = os.path.expanduser("~")
        assert _shorten_path(f"{home}/foo/bar") == "~/foo/bar"

    def test_shorten_non_home(self) -> None:
        assert _shorten_path("/tmp/foo") == "/tmp/foo"

    def test_shorten_empty(self) -> None:
        assert _shorten_path("") == ""

    def test_shorten_home_root(self) -> None:
        """Home directory itself should become '~'."""
        home = os.path.expanduser("~")
        assert _shorten_path(home) == "~"
