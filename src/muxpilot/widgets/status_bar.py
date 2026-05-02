"""Status bar showing summary statistics and latest events."""

from __future__ import annotations

from textual.widgets import Static

from muxpilot.models import PaneStatus, STATUS_ICONS, TmuxTree, TmuxEvent


class StatusBar(Static):
    """Bottom status bar showing tmux statistics and event notifications."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 2;
        background: $primary-background;
        color: $text;
        padding: 0 1;
    }
    """

    # Icon legend labels
    _STATUS_LABELS: dict[PaneStatus, str] = {
        PaneStatus.ACTIVE: "active",
        PaneStatus.WAITING_INPUT: "waiting",
        PaneStatus.ERROR: "error",
        PaneStatus.IDLE: "idle",
    }

    def __init__(self, name: str | None = None, id: str | None = None) -> None:
        super().__init__("", name=name, id=id)
        self._last_event: str = ""

    @staticmethod
    def _icon_legend() -> str:
        """Build the icon→status legend string."""
        parts = []
        for s in PaneStatus:
            icon = STATUS_ICONS[s]
            label = StatusBar._STATUS_LABELS[s]
            if s == PaneStatus.ERROR:
                parts.append(f"[red]{icon}:{label}[/red]")
            else:
                parts.append(f"{icon}:{label}")
        return "  ".join(parts)

    def update_stats(self, tree: TmuxTree) -> None:
        """Update the status bar with tree statistics."""
        # Count panes by status
        status_counts: dict[PaneStatus, int] = {}
        for pane in tree.all_panes():
            status_counts[pane.status] = status_counts.get(pane.status, 0) + 1

        parts = [
            f"■ {tree.total_sessions}",
            f"□ {tree.total_windows}",
            f"▣ {tree.total_panes}",
        ]

        # Add status breakdown if any panes have known status
        for status in [PaneStatus.ACTIVE, PaneStatus.WAITING_INPUT, PaneStatus.ERROR, PaneStatus.IDLE]:
            count = status_counts.get(status, 0)
            if count > 0:
                icon = STATUS_ICONS[status]
                if status == PaneStatus.ERROR:
                    parts.append(f"[red]{icon} {count}[/red]")
                else:
                    parts.append(f"{icon} {count}")

        status_text = "  ".join(parts)

        if self._last_event:
            status_text += f"  │  {self._last_event}"

        status_text += f"\n{self._icon_legend()}"

        self.update(status_text)

    def show_event(self, event: TmuxEvent) -> None:
        """Display a transient event notification."""
        self._last_event = event.message
