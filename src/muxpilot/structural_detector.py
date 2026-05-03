"""Detect structural changes between two TmuxTree snapshots."""

from __future__ import annotations

from muxpilot.models import TmuxEvent, TmuxTree


class StructuralChangeDetector:
    """Detects additions/removals of sessions, windows, panes, and focus changes."""

    def detect(self, old_tree: TmuxTree, new_tree: TmuxTree) -> list[TmuxEvent]:
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
