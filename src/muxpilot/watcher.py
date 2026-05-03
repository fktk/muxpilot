"""Pane output watcher for detecting activity and status changes."""

from __future__ import annotations

import hashlib
import os
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
from muxpilot.tmux_client import TmuxClient


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
        self.activities: dict[str, PaneActivity] = {}
        self._config_error: str | None = None
        self.notify_poll_errors: bool = True

        # Load default patterns
        self.prompt_patterns = list(DEFAULT_PROMPT_PATTERNS)
        self.error_patterns = list(DEFAULT_ERROR_PATTERNS)
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
                        self.prompt_patterns = [re.compile(p) for p in custom_prompts]

                    custom_errors = watcher_cfg.get("error_patterns", [])
                    if custom_errors:
                        self.error_patterns = [re.compile(p) for p in custom_errors]

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

        self._last_tree: TmuxTree | None = None
        self._last_poll_time: float | None = None

    @property
    def config_error(self) -> str | None:
        """Return the config loading error message, if any."""
        return self._config_error

    @property
    def config_error(self) -> str | None:
        """Return the config loading error message, if any."""
        return self._config_error

    def poll(self) -> tuple[TmuxTree, list[TmuxEvent]]:
        """
        Perform one poll cycle:
        1. Fetch the current tmux tree
        2. Detect structural changes (pane/window/session add/remove)
        3. Capture pane output and detect status changes
        4. Return updated tree and events
        """
        new_tree = self.client.get_tree()
        events: list[TmuxEvent] = []

        # Detect structural changes
        if self._last_tree is not None:
            events.extend(self._detect_structural_changes(self._last_tree, new_tree))

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
            old_activity = self.activities.get(pane.pane_id)
            new_activity = self._analyze_pane(pane.pane_id, content, old_activity, poll_elapsed)

            old_status = old_activity.status if old_activity else PaneStatus.ACTIVE
            new_status = self._determine_status(
                content,
                new_activity.last_line,
                new_activity.idle_seconds,
                old_status,
                new_activity.content_changed,
            )
            new_activity.status = new_status

            # Check for status change
            if old_activity and old_activity.status != new_activity.status:
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
            self.activities[pane.pane_id] = new_activity

        # Clean up activities for removed panes
        current_pane_ids = {p.pane_id for p in new_tree.all_panes()}
        for pane_id in list(self.activities.keys()):
            if pane_id not in current_pane_ids:
                del self.activities[pane_id]

        self._last_tree = new_tree
        self._last_poll_time = now
        return new_tree, events

    def _analyze_pane(
        self,
        pane_id: str,
        content: list[str],
        old_activity: PaneActivity | None,
        poll_elapsed: float,
    ) -> PaneActivity:
        """Analyze pane content and track idle time."""
        content_str = "\n".join(content)
        content_hash = hashlib.md5(content_str.encode()).hexdigest()
        last_line = content[-1].strip() if content else ""
        recent_lines = content[-self.preview_lines:] if content else []

        content_changed = not (old_activity and old_activity.last_content_hash == content_hash)

        if old_activity and not content_changed:
            idle_seconds = old_activity.idle_seconds + poll_elapsed
        else:
            idle_seconds = 0.0

        return PaneActivity(
            pane_id=pane_id,
            last_content_hash=content_hash,
            last_line=last_line,
            idle_seconds=idle_seconds,
            status=old_activity.status if old_activity else PaneStatus.ACTIVE,
            content_changed=content_changed,
            recent_lines=recent_lines,
        )

    def _determine_status(
        self,
        content: list[str],
        last_line: str,
        idle_seconds: float,
        old_status: PaneStatus,
        content_changed: bool,
    ) -> PaneStatus:
        """Determine the pane status based on output patterns.

        Once a pane leaves ACTIVE, it keeps its status until content changes.
        """
        # If content hasn't changed and we were already in a non-ACTIVE state,
        # preserve that status until new activity resets us.
        if not content_changed and old_status != PaneStatus.ACTIVE:
            return old_status

        # Check for error patterns in recent output
        recent_lines = content[-10:] if content else []
        for line in recent_lines:
            for pattern in self.error_patterns:
                if pattern.search(line):
                    return PaneStatus.ERROR

        # Check if the last line looks like a prompt (waiting for input)
        for pattern in self.prompt_patterns:
            if pattern.search(last_line):
                return PaneStatus.WAITING_INPUT

        # Check if the pane has been idle long enough
        if idle_seconds >= self.idle_threshold:
            return PaneStatus.IDLE

        return PaneStatus.ACTIVE

    def _detect_structural_changes(
        self,
        old_tree: TmuxTree,
        new_tree: TmuxTree,
    ) -> list[TmuxEvent]:
        """Detect additions/removals of sessions, windows, panes, and focus changes."""
        events: list[TmuxEvent] = []

        old_pane_ids = {p.pane_id for p in old_tree.all_panes()}
        new_pane_ids = {p.pane_id for p in new_tree.all_panes()}

        for pane_id in new_pane_ids - old_pane_ids:
            events.append(
                TmuxEvent(
                    event_type="pane_added",
                    pane_id=pane_id,
                    message=f"Pane added: {pane_id}",
                )
            )

        for pane_id in old_pane_ids - new_pane_ids:
            events.append(
                TmuxEvent(
                    event_type="pane_removed",
                    pane_id=pane_id,
                    message=f"Pane removed: {pane_id}",
                )
            )

        old_session_names = {s.session_name for s in old_tree.sessions}
        new_session_names = {s.session_name for s in new_tree.sessions}

        for name in new_session_names - old_session_names:
            events.append(
                TmuxEvent(
                    event_type="session_added",
                    session_name=name,
                    message=f"Session added: {name}",
                )
            )

        for name in old_session_names - new_session_names:
            events.append(
                TmuxEvent(
                    event_type="session_removed",
                    session_name=name,
                    message=f"Session removed: {name}",
                )
            )

        # Detect active pane (focus) changes
        old_active = {p.pane_id for p in old_tree.all_panes() if p.is_active}
        new_active = {p.pane_id for p in new_tree.all_panes() if p.is_active}
        if old_active != new_active:
            for pane_id in new_active - old_active:
                events.append(
                    TmuxEvent(
                        event_type="focus_changed",
                        pane_id=pane_id,
                        message=f"Focus changed to: {pane_id}",
                    )
                )

        return events

    def process_notification(self, message: str) -> TmuxEvent | None:
        """Parse a notification message and update pane status if it matches.

        Returns a TmuxEvent on status change, or None if no match.
        """
        if self.waiting_trigger_pattern is None:
            return None

        # Find first pane id token
        pane_match = re.search(r"%[0-9]+", message)
        if not pane_match:
            return None
        pane_id = pane_match.group(0)

        # Check pattern match
        if not self.waiting_trigger_pattern.search(message):
            return None

        activity = self.activities.get(pane_id)
        if activity is None:
            return None

        old_status = activity.status
        activity.status = PaneStatus.WAITING_INPUT

        return TmuxEvent(
            event_type="status_changed",
            pane_id=pane_id,
            old_status=old_status,
            new_status=PaneStatus.WAITING_INPUT,
            message=f"{pane_id}: {old_status.value} → waiting",
        )
