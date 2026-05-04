"""Track pane activity over time (content hashes, idle time, recent lines)."""

from __future__ import annotations

import hashlib
import logging
import time

from muxpilot.models import PaneActivity, PaneStatus

logger = logging.getLogger(__name__)


class StatusTracker:
    """Tracks pane output changes for status detection."""

    def __init__(self, preview_lines: int = 50) -> None:
        self.preview_lines = preview_lines
        self.activities: dict[str, PaneActivity] = {}

    def analyze_pane(
        self,
        pane_id: str,
        content: list[str],
        old_activity: PaneActivity | None,
        poll_elapsed: float,
        now: float | None = None,
    ) -> PaneActivity:
        """Analyze pane content and track idle time."""
        if now is None:
            now = time.time()

        content_str = "\n".join(content)
        content_hash = hashlib.md5(content_str.encode()).hexdigest()
        last_line = content[-1].strip() if content else ""
        recent_lines = content[-self.preview_lines:] if content else []

        content_changed = not (old_activity and old_activity.last_content_hash == content_hash)

        logger.debug(
            "analyze_pane pane=%s hash=%s content_changed=%s",
            pane_id,
            content_hash[:8],
            content_changed,
        )

        if old_activity and not content_changed:
            idle_seconds = old_activity.idle_seconds + poll_elapsed
        else:
            idle_seconds = 0.0

        logger.debug("analyze_pane pane=%s idle_seconds=%.2f", pane_id, idle_seconds)

        status_override = old_activity.status_override if old_activity else None
        status_override_until = old_activity.status_override_until if old_activity else 0.0
        if content_changed and status_override is not None and now >= status_override_until:
            logger.debug(
                "analyze_pane pane=%s status_override cleared (content_changed)",
                pane_id,
            )
            status_override = None

        activity = PaneActivity(
            pane_id=pane_id,
            last_content_hash=content_hash,
            last_line=last_line,
            idle_seconds=idle_seconds,
            status=old_activity.status if old_activity else PaneStatus.ACTIVE,
            content_changed=content_changed,
            recent_lines=recent_lines,
            status_override=status_override,
            status_override_until=status_override_until,
        )
        self.activities[pane_id] = activity
        return activity

    def cleanup_removed(self, current_pane_ids: set[str]) -> None:
        """Remove activities for panes that no longer exist."""
        for pane_id in list(self.activities.keys()):
            if pane_id not in current_pane_ids:
                del self.activities[pane_id]
