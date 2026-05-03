"""Pane output watcher for detecting activity and status changes."""

from __future__ import annotations

import logging
import pathlib
import re
import time
import tomllib

from muxpilot.models import (
    PaneActivity,
    PaneStatus,
    TmuxEvent,
    TmuxTree,
)
from muxpilot.pattern_matcher import PatternMatcher
from muxpilot.status_tracker import StatusTracker
from muxpilot.structural_detector import StructuralChangeDetector
from muxpilot.tmux_client import TmuxClient

logger = logging.getLogger(__name__)


# Default patterns for status detection
DEFAULT_PROMPT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"[\$#>%]\s*$"),                    # Common shell prompts
    re.compile(r"\(y/n\)\s*$", re.IGNORECASE),     # Yes/No prompts
    re.compile(r"\?\s*$"),                          # Question prompts
    re.compile(r">>>\s*$"),                         # Python REPL
    re.compile(r"\.\.\.\s*$"),                      # Python continuation
    re.compile(r"In \[\d+\]:\s*$"),                 # IPython/Jupyter
    re.compile(r"Press .* to continue", re.IGNORECASE),  # Pause prompts
]

DEFAULT_ERROR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:Error|ERROR|error)[:.\s]"),
    re.compile(r"(?:Exception|EXCEPTION)[:.\s]"),
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r"FAIL(?:ED|URE)?[:.\s]"),
    re.compile(r"panic[:.\s]"),
    re.compile(r"FATAL[:.\s]"),
    re.compile(r"Segmentation fault"),
]

# Idle threshold in seconds before a pane is considered idle
DEFAULT_IDLE_THRESHOLD: float = 10.0
DEFAULT_POLL_INTERVAL: float = 5.0


class TmuxWatcher:
    """Monitors pane outputs via polling and detects status changes."""

    def __init__(
        self,
        client: TmuxClient,
        idle_threshold: float = DEFAULT_IDLE_THRESHOLD,
        capture_lines: int = 30,
        config_path: pathlib.Path | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        preview_lines: int = 30,
    ) -> None:
        self.client = client
        self.idle_threshold = idle_threshold
        self.capture_lines = capture_lines
        self.poll_interval = poll_interval
        self.preview_lines = preview_lines
        self._config_error: str | None = None
        self.notify_poll_errors: bool = True

        # Load default patterns
        prompt_patterns = list(DEFAULT_PROMPT_PATTERNS)
        error_patterns = list(DEFAULT_ERROR_PATTERNS)
        self.waiting_trigger_pattern: re.Pattern[str] | None = None

        # Override with config if present
        if config_path is None:
            config_path = pathlib.Path.home() / ".config/muxpilot/config.toml"
        if config_path.exists():
            try:
                with open(config_path, "rb") as f:
                    config = tomllib.load(f)
                    watcher_cfg = config.get("watcher", {})

                    custom_prompts = watcher_cfg.get("prompt_patterns", [])
                    if custom_prompts:
                        prompt_patterns = [re.compile(p) for p in custom_prompts]

                    custom_errors = watcher_cfg.get("error_patterns", [])
                    if custom_errors:
                        error_patterns = [re.compile(p) for p in custom_errors]

                    self.idle_threshold = watcher_cfg.get("idle_threshold", self.idle_threshold)
                    self.poll_interval = watcher_cfg.get("poll_interval", self.poll_interval)

                    notify_cfg = config.get("notifications", {})
                    if "poll_errors" in notify_cfg:
                        self.notify_poll_errors = bool(notify_cfg["poll_errors"])

                    waiting_pattern = notify_cfg.get("waiting_trigger_pattern", "")
                    if waiting_pattern:
                        self.waiting_trigger_pattern = re.compile(waiting_pattern)
            except Exception as e:
                self._config_error = str(e)

        self._matcher = PatternMatcher(
            prompt_patterns=prompt_patterns,
            error_patterns=error_patterns,
            idle_threshold=self.idle_threshold,
        )
        self._tracker = StatusTracker(preview_lines=preview_lines)
        self._detector = StructuralChangeDetector()

        self._last_tree: TmuxTree | None = None
        self._last_poll_time: float | None = None

    @property
    def config_error(self) -> str | None:
        """Return the config loading error message, if any."""
        return self._config_error

    @property
    def prompt_patterns(self) -> list[re.Pattern[str]]:
        """Access prompt patterns (backward compatibility)."""
        return self._matcher.prompt_patterns

    @property
    def error_patterns(self) -> list[re.Pattern[str]]:
        """Access error patterns (backward compatibility)."""
        return self._matcher.error_patterns

    @property
    def activities(self) -> dict[str, PaneActivity]:
        """Access the underlying activity tracker state (for backward compatibility)."""
        return self._tracker.activities

    @activities.setter
    def activities(self, value: dict[str, PaneActivity]) -> None:
        """Replace the activity tracker state (for tests)."""
        self._tracker.activities = value

    def poll(self) -> tuple[TmuxTree, list[TmuxEvent]]:
        """
        Perform one poll cycle:
        1. Fetch the current tmux tree
        2. Detect structural changes (pane/window/session add/remove)
        3. Capture pane output and detect status changes
        4. Return updated tree and events
        """
        logger.debug("poll start")
        new_tree = self.client.get_tree()
        events: list[TmuxEvent] = []

        # Detect structural changes
        if self._last_tree is not None:
            events.extend(self._detector.detect(self._last_tree, new_tree))

        # Analyze pane outputs and detect status changes
        current_pane_id = self.client.get_current_pane_id()
        now = time.time()
        poll_elapsed = now - self._last_poll_time if self._last_poll_time is not None else 0.0

        for pane in new_tree.all_panes():
            # Skip our own pane
            if pane.pane_id == current_pane_id:
                pane.status = PaneStatus.ACTIVE
                continue

            content = self.client.capture_pane_content(pane.pane_id, self.capture_lines)
            old_activity = self._tracker.activities.get(pane.pane_id)
            new_activity = self._tracker.analyze_pane(pane.pane_id, content, old_activity, poll_elapsed)

            old_status = old_activity.status if old_activity else PaneStatus.ACTIVE
            new_status = self._matcher.determine_status(
                content,
                new_activity.last_line,
                new_activity.idle_seconds,
                old_status,
                new_activity.content_changed,
            )
            # If status_override is set, use it instead of the auto-determined status
            if new_activity.status_override is not None:
                logger.debug(
                    "poll pane=%s status_override=%s → %s",
                    pane.pane_id,
                    new_status.value,
                    new_activity.status_override.value,
                )
                new_status = new_activity.status_override
            new_activity.status = new_status

            # Check for status change
            if old_activity and old_activity.status != new_activity.status:
                logger.debug(
                    "poll pane=%s status changed %s → %s",
                    pane.pane_id,
                    old_activity.status.value,
                    new_activity.status.value,
                )
                events.append(
                    TmuxEvent(
                        event_type="status_changed",
                        pane_id=pane.pane_id,
                        old_status=old_activity.status,
                        new_status=new_activity.status,
                        message=f"{pane.pane_id}: {old_activity.status.value} → {new_activity.status.value}",
                    )
                )

            pane.status = new_activity.status
            pane.idle_seconds = new_activity.idle_seconds
            pane.recent_lines = new_activity.recent_lines

        # Clean up activities for removed panes
        current_pane_ids = {p.pane_id for p in new_tree.all_panes()}
        self._tracker.cleanup_removed(current_pane_ids)

        self._last_tree = new_tree
        self._last_poll_time = now
        logger.debug("poll end events=%d", len(events))
        return new_tree, events

    def process_notification(self, message: str) -> TmuxEvent | None:
        """Parse a notification message and update pane status if it matches.

        Returns a TmuxEvent when both pane id and pattern are found, or None if no match.
        """
        logger.debug("process_notification message=%r", message)

        if self.waiting_trigger_pattern is None:
            logger.debug("process_notification skipped: no waiting_trigger_pattern")
            return None

        # Find first pane id token
        pane_match = re.search(r"%[0-9]+", message)
        if not pane_match:
            logger.debug("process_notification skipped: no pane_id found")
            return None
        pane_id = pane_match.group(0)

        # Check pattern match
        if not self.waiting_trigger_pattern.search(message):
            logger.debug("process_notification skipped: pattern did not match")
            return None

        activity = self._tracker.activities.get(pane_id)
        if activity is None:
            logger.debug("process_notification skipped: unknown pane %s", pane_id)
            return None

        old_status = activity.status
        activity.status = PaneStatus.WAITING_INPUT
        activity.status_override = PaneStatus.WAITING_INPUT
        logger.debug(
            "process_notification pane=%s status=%s → WAITING_INPUT (override set)",
            pane_id,
            old_status.value,
        )

        return TmuxEvent(
            event_type="status_changed",
            pane_id=pane_id,
            old_status=old_status,
            new_status=PaneStatus.WAITING_INPUT,
            message=f"{pane_id}: {old_status.value} → {PaneStatus.WAITING_INPUT.value}",
        )
