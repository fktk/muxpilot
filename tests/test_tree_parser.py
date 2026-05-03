"""Tests for muxpilot.tree_parser — TSV parsing of tmux list-panes output."""

from __future__ import annotations

import pytest

from muxpilot.tree_parser import TreeParser
from muxpilot.models import TmuxTree


class TestTreeParser:
    """Tests for parsing tmux list-panes -F output into TmuxTree."""

    def test_basic_single_pane(self):
        """Single session/window/pane should parse correctly."""
        stdout = "dev\t$0\t1\t@0\teditor\t0\t1\t%0\t0\tbash\t/home/user\t1\t80\t24\t1234\tmy-pane"
        tree = TreeParser.parse_list_panes_output(stdout, self_pane_id=None)
        assert tree.total_sessions == 1
        assert tree.total_windows == 1
        assert tree.total_panes == 1
        assert tree.sessions[0].session_name == "dev"
        assert tree.sessions[0].session_id == "$0"
        assert tree.sessions[0].is_attached is True
        assert tree.sessions[0].windows[0].window_name == "editor"
        assert tree.sessions[0].windows[0].panes[0].pane_id == "%0"
        assert tree.sessions[0].windows[0].panes[0].pane_title == "my-pane"

    def test_multiple_sessions_windows_panes(self):
        """Multiple sessions, windows, and panes should group correctly."""
        lines = [
            "s0\t$0\t1\t@0\tw0\t0\t1\t%0\t0\tbash\t/home/user\t1\t80\t24\t1234\tp0",
            "s0\t$0\t1\t@0\tw0\t0\t1\t%1\t1\tvim\t/home/user\t0\t80\t24\t1235\tp1",
            "s0\t$0\t1\t@1\tw1\t1\t0\t%2\t0\tpython\t/home/user\t1\t80\t24\t1236\tp2",
            "s1\t$1\t0\t@2\tw2\t0\t1\t%3\t0\tzsh\t/home/user\t1\t80\t24\t1237\tp3",
        ]
        tree = TreeParser.parse_list_panes_output("\n".join(lines), self_pane_id=None)
        assert tree.total_sessions == 2
        assert tree.total_windows == 3
        assert tree.total_panes == 4

    def test_empty_output(self):
        """Empty stdout should produce an empty tree."""
        tree = TreeParser.parse_list_panes_output("", self_pane_id=None)
        assert tree.total_sessions == 0
        assert tree.total_windows == 0
        assert tree.total_panes == 0

    def test_none_values(self):
        """Tab-only line should not crash and produce zero/empty defaults."""
        stdout = "\t" * 15
        tree = TreeParser.parse_list_panes_output(stdout, self_pane_id=None)
        assert tree.total_sessions == 1
        assert tree.total_windows == 1
        assert tree.total_panes == 1
        pane = tree.sessions[0].windows[0].panes[0]
        assert pane.current_command == ""
        assert pane.current_path == ""
        assert pane.width == 0
        assert pane.height == 0
        assert pane.pane_index == 0
        assert pane.is_active is False

    def test_self_pane_marking(self):
        """Pane matching self_pane_id should have is_self=True."""
        stdout = "dev\t$0\t1\t@0\teditor\t0\t1\t%5\t0\tbash\t/home/user\t1\t80\t24\t1234\t"
        tree = TreeParser.parse_list_panes_output(stdout, self_pane_id="%5")
        assert tree.sessions[0].windows[0].panes[0].is_self is True

    def test_non_self_pane(self):
        """Pane not matching self_pane_id should have is_self=False."""
        stdout = "dev\t$0\t1\t@0\teditor\t0\t1\t%5\t0\tbash\t/home/user\t1\t80\t24\t1234\t"
        tree = TreeParser.parse_list_panes_output(stdout, self_pane_id="%99")
        assert tree.sessions[0].windows[0].panes[0].is_self is False

    def test_skips_short_lines(self):
        """Lines with fewer than 16 fields should be skipped."""
        stdout = "dev\t$0\t1\t@0\teditor\t0\t1\t%0\t0\tbash\t/home/user\t1\t80\t24"
        tree = TreeParser.parse_list_panes_output(stdout, self_pane_id=None)
        assert tree.total_sessions == 0

    def test_window_active_flag(self):
        """window_active=0 should produce is_active=False."""
        stdout = "dev\t$0\t1\t@0\teditor\t0\t0\t%0\t0\tbash\t/home/user\t1\t80\t24\t1234\t"
        tree = TreeParser.parse_list_panes_output(stdout, self_pane_id=None)
        assert tree.sessions[0].windows[0].is_active is False

    def test_session_attached_flag(self):
        """session_attached=0 should produce is_attached=False."""
        stdout = "dev\t$0\t0\t@0\teditor\t0\t1\t%0\t0\tbash\t/home/user\t1\t80\t24\t1234\t"
        tree = TreeParser.parse_list_panes_output(stdout, self_pane_id=None)
        assert tree.sessions[0].is_attached is False
