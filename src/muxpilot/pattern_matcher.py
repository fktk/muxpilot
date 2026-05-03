"""Pattern-based status detection for pane output."""

from __future__ import annotations

import re

from muxpilot.models import PaneStatus


class PatternMatcher:
    """Determines pane status based on output patterns (prompts, errors, idle)."""

    def __init__(
        self,
        prompt_patterns: list[re.Pattern[str]],
        error_patterns: list[re.Pattern[str]],
        idle_threshold: float,
    ) -> None:
        self.prompt_patterns = prompt_patterns
        self.error_patterns = error_patterns
        self.idle_threshold = idle_threshold

    def determine_status(
        self,
        content: list[str],
        last_line: str,
        idle: float,
        old_status: PaneStatus,
        content_changed: bool,
    ) -> PaneStatus:
        """Determine the pane status based on output patterns.

        Once a pane leaves ACTIVE, it keeps its status until content changes.
        """
        if not content_changed and old_status != PaneStatus.ACTIVE:
            return old_status

        recent_lines = content[-10:] if content else []
        for line in recent_lines:
            for pattern in self.error_patterns:
                if pattern.search(line):
                    return PaneStatus.ERROR

        for pattern in self.prompt_patterns:
            if pattern.search(last_line):
                return PaneStatus.WAITING_INPUT

        if idle >= self.idle_threshold:
            return PaneStatus.IDLE

        return PaneStatus.ACTIVE
