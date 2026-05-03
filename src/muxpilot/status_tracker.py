"""Track pane activity over time (content hashes, idle time, recent lines)."""

from __future__ import annotations

import hashlib

from muxpilot.models import PaneActivity, PaneStatus


class StatusTracker:
    """Tracks pane output changes for status detection."""

    def __init__(self, preview_lines: int = 30) -> None:
        self.preview_lines = preview_lines
        self.activities: dict[str, PaneActivity] = {}

    def analyze_pane(
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

        status_override = old_activity.status_override if old_activity else None
        if content_changed and status_override is not None:
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
        )
        self.activities[pane_id] = activity
        return activity

    def cleanup_removed(self, current_pane_ids: set[str]) -> None:
        """Remove activities for panes that no longer exist."""
        for pane_id in list(self.activities.keys()):
            if pane_id not in current_pane_ids:
                del self.activities[pane_id]
