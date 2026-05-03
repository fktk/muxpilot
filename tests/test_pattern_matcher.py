"""Tests for muxpilot.pattern_matcher — status determination from pane output."""

from __future__ import annotations

import re

import pytest

from muxpilot.pattern_matcher import PatternMatcher
from muxpilot.models import PaneStatus


class TestPatternMatcher:
    """Tests for PatternMatcher.determine_status."""

    @pytest.fixture
    def matcher(self):
        return PatternMatcher(
            prompt_patterns=[
                re.compile(r"[\$#>%]\s*$"),
                re.compile(r"\(y/n\)\s*$", re.IGNORECASE),
                re.compile(r"\?\s*$"),
                re.compile(r">>>\s*$"),
                re.compile(r"\.\.\.\s*$"),
                re.compile(r"In \[\d+\]:\s*$"),
                re.compile(r"Press .* to continue", re.IGNORECASE),
            ],
            error_patterns=[
                re.compile(r"(?:Error|ERROR|error)[:.\s]"),
                re.compile(r"(?:Exception|EXCEPTION)[:.\s]"),
                re.compile(r"Traceback \(most recent call last\)"),
                re.compile(r"FAIL(?:ED|URE)?[:.\s]"),
                re.compile(r"panic[:.\s]"),
                re.compile(r"FATAL[:.\s]"),
                re.compile(r"Segmentation fault"),
            ],
            idle_threshold=10.0,
        )

    def test_active_when_content_changing(self, matcher):
        assert matcher.determine_status(["output"], "output", idle=0.0, old_status=PaneStatus.ACTIVE, content_changed=True) == PaneStatus.ACTIVE

    def test_idle_when_no_change(self, matcher):
        assert matcher.determine_status(["output"], "output", idle=15.0, old_status=PaneStatus.ACTIVE, content_changed=False) == PaneStatus.IDLE

    def test_idle_threshold_not_met_stays_active(self, matcher):
        assert matcher.determine_status(["output"], "output", idle=5.0, old_status=PaneStatus.ACTIVE, content_changed=False) == PaneStatus.ACTIVE

    def test_completed_shell_prompt(self, matcher):
        assert matcher.determine_status(["user@host:~$ "], "user@host:~$ ", idle=0.0, old_status=PaneStatus.ACTIVE, content_changed=True) == PaneStatus.WAITING_INPUT

    def test_waiting_shell_prompt(self, matcher):
        assert matcher.determine_status(["user@host:~$ "], "user@host:~$ ", idle=15.0, old_status=PaneStatus.ACTIVE, content_changed=True) == PaneStatus.WAITING_INPUT

    def test_waiting_python_repl(self, matcher):
        assert matcher.determine_status([">>> "], ">>> ", idle=15.0, old_status=PaneStatus.ACTIVE, content_changed=True) == PaneStatus.WAITING_INPUT

    def test_waiting_ipython(self, matcher):
        assert matcher.determine_status(["In [1]: "], "In [1]: ", idle=15.0, old_status=PaneStatus.ACTIVE, content_changed=True) == PaneStatus.WAITING_INPUT

    def test_waiting_yes_no(self, matcher):
        assert matcher.determine_status(["Continue? (y/n) "], "Continue? (y/n) ", idle=15.0, old_status=PaneStatus.ACTIVE, content_changed=True) == PaneStatus.WAITING_INPUT

    def test_error_traceback(self, matcher):
        lines = ["some code", "Traceback (most recent call last)", "  File ..."]
        assert matcher.determine_status(lines, "  File ...", idle=0.0, old_status=PaneStatus.ACTIVE, content_changed=True) == PaneStatus.ERROR

    def test_error_exception(self, matcher):
        lines = ["ValueError: invalid literal"]
        assert matcher.determine_status(lines, lines[-1], idle=0.0, old_status=PaneStatus.ACTIVE, content_changed=True) == PaneStatus.ERROR

    def test_error_failed(self, matcher):
        lines = ["FAILED: test_xyz"]
        assert matcher.determine_status(lines, lines[-1], idle=0.0, old_status=PaneStatus.ACTIVE, content_changed=True) == PaneStatus.ERROR

    def test_error_panic(self, matcher):
        lines = ["panic: runtime error"]
        assert matcher.determine_status(lines, lines[-1], idle=0.0, old_status=PaneStatus.ACTIVE, content_changed=True) == PaneStatus.ERROR

    def test_error_segfault(self, matcher):
        lines = ["Segmentation fault"]
        assert matcher.determine_status(lines, lines[-1], idle=0.0, old_status=PaneStatus.ACTIVE, content_changed=True) == PaneStatus.ERROR

    def test_error_fatal(self, matcher):
        lines = ["FATAL: cannot start"]
        assert matcher.determine_status(lines, lines[-1], idle=0.0, old_status=PaneStatus.ACTIVE, content_changed=True) == PaneStatus.ERROR

    def test_error_takes_priority_over_prompt(self, matcher):
        lines = ["Error: something failed", "user@host:~$ "]
        assert matcher.determine_status(lines, "user@host:~$ ", idle=15.0, old_status=PaneStatus.ACTIVE, content_changed=True) == PaneStatus.ERROR

    def test_error_persists_when_no_change(self, matcher):
        assert matcher.determine_status(["Error: old"], "Error: old", idle=60.0, old_status=PaneStatus.ERROR, content_changed=False) == PaneStatus.ERROR

    def test_waiting_persists_when_no_change(self, matcher):
        assert matcher.determine_status(["$ "], "$ ", idle=60.0, old_status=PaneStatus.WAITING_INPUT, content_changed=False) == PaneStatus.WAITING_INPUT

    def test_error_resets_on_change_without_pattern(self, matcher):
        assert matcher.determine_status(["normal output"], "normal output", idle=0.0, old_status=PaneStatus.ERROR, content_changed=True) == PaneStatus.ACTIVE

    def test_waiting_resets_on_change_without_pattern(self, matcher):
        assert matcher.determine_status(["normal output"], "normal output", idle=0.0, old_status=PaneStatus.WAITING_INPUT, content_changed=True) == PaneStatus.ACTIVE

    def test_empty_content(self, matcher):
        assert matcher.determine_status([], "", idle=0.0, old_status=PaneStatus.ACTIVE, content_changed=True) == PaneStatus.ACTIVE

    def test_only_whitespace_lines(self, matcher):
        lines = ["   ", "  ", ""]
        assert matcher.determine_status(lines, "", idle=0.0, old_status=PaneStatus.ACTIVE, content_changed=True) == PaneStatus.ACTIVE
