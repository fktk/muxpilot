"""Status bar showing summary statistics and latest events."""

from __future__ import annotations

from textual.widgets import Static

from muxpilot.models import PaneStatus, STATUS_ICONS, TmuxTree, TmuxEvent


class StatusBar(Static):
    """Bottom status bar showing tmux statistics and event notifications."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: $primary-background;
        color: $text;
        padding: 0 1;
    }
    """

    def __init__(self, name: str | None = None, id: str | None = None) -> None:
        super().__init__("", name=name, id=id)
        self._last_event: str = ""

    def update_stats(self, tree: TmuxTree) -> None:
        """Update the status bar with tree statistics."""
        # Count panes by status
        status_counts: dict[PaneStatus, int] = {}
        for pane in tree.all_panes():
            status_counts[pane.status] = status_counts.get(pane.status, 0) + 1

        parts = [
            f"📦 {tree.total_sessions}",
            f"🪟 {tree.total_windows}",
            f"▣ {tree.total_panes}",
        ]

        # Add status breakdown if any panes have known status
        for status in [PaneStatus.ACTIVE, PaneStatus.WAITING_INPUT, PaneStatus.ERROR]:
            count = status_counts.get(status, 0)
            if count > 0:
                icon = STATUS_ICONS[status]
                parts.append(f"{icon} {count}")

        status_text = "  ".join(parts)

        if self._last_event:
            status_text += f"  │  {self._last_event}"

        self.update(status_text)

    def show_event(self, event: TmuxEvent) -> None:
        """Display a transient event notification."""
        self._last_event = event.message
