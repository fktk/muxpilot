"""Pattern-based status detection for pane output."""

from __future__ import annotations

import logging
import re

from muxpilot.models import PaneStatus

logger = logging.getLogger(__name__)


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
        logger.debug(
            "determine_status last_line=%r idle=%.2f old_status=%s content_changed=%s",
            last_line,
            idle,
            old_status.value,
            content_changed,
        )

        if not content_changed and old_status != PaneStatus.ACTIVE:
            logger.debug("hysteresis: preserving %s", old_status.value)
            return old_status

        recent_lines = content[-10:] if content else []
        for line in recent_lines:
            for pattern in self.error_patterns:
                if pattern.search(line):
                    logger.debug("error pattern matched: %r → ERROR", line[:40])
                    return PaneStatus.ERROR

        for pattern in self.prompt_patterns:
            if pattern.search(last_line):
                logger.debug("prompt pattern matched: %r → WAITING_INPUT", last_line[:40])
                return PaneStatus.WAITING_INPUT

        if idle >= self.idle_threshold:
            logger.debug("idle threshold reached (%.2f >= %.2f) → IDLE", idle, self.idle_threshold)
            return PaneStatus.IDLE

        logger.debug("fallback to ACTIVE")
        return PaneStatus.ACTIVE
