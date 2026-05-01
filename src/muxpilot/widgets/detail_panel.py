"""Detail panel showing information about the selected tree node."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static

from muxpilot.models import (
    PaneInfo,
    PaneStatus,
    STATUS_ICONS,
    SessionInfo,
    WindowInfo,
    _shorten_path,
)


class DetailPanel(Widget):
    """Displays detailed information about the currently selected tree node."""

    DEFAULT_CSS = """
    DetailPanel {
        width: 1fr;
        height: 1fr;
        padding: 1 2;
    }

    DetailPanel .detail-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    DetailPanel .detail-row {
        margin-bottom: 0;
    }

    DetailPanel .detail-label {
        color: $text-muted;
    }
    """

    def __init__(self, name: str | None = None, id: str | None = None) -> None:
        super().__init__(name=name, id=id)
        self._content = Static("Select a node to see details", id="detail-content")

    def compose(self) -> ComposeResult:
        yield self._content

    def show_pane(self, pane: PaneInfo, window: WindowInfo, session: SessionInfo) -> None:
        """Display pane details."""
        icon = STATUS_ICONS.get(pane.status, "?")
        status_name = pane.status.value if pane.status else "unknown"
        idle_text = f" ({pane.idle_seconds:.1f}s idle)" if pane.idle_seconds > 0 else ""
        title = pane.pane_title or "—"
        repo = pane.repo_name or "—"
        branch = pane.branch or "—"

        text = (
            f"[bold $accent]── Pane ──[/]\n"
            f"\n"
            f"  [dim]Title:[/]       {title}\n"
            f"  [dim]Repository:[/]  {repo}\n"
            f"  [dim]Branch:[/]      {branch}\n"
            f"  [dim]Command:[/]     {pane.full_command or pane.current_command}\n"
            f"  [dim]Path:[/]        {_shorten_path(pane.current_path)}\n"
            f"  [dim]Size:[/]        {pane.width}×{pane.height}\n"
            f"  [dim]Active:[/]      {'Yes' if pane.is_active else 'No'}\n"
            f"  [dim]Status:[/]      {icon} {status_name}{idle_text}\n"
        )

        if pane.status == PaneStatus.ERROR:
            text += "\n  [bold $error]Status is ERROR[/]\n"
        elif pane.status == PaneStatus.WAITING_INPUT:
            text += "\n  [bold $warning]Waiting for input[/]\n"

        text += (
            f"\n"
            f"[bold $accent]── Recent Output ──[/]\n"
        )
        preview = pane.recent_lines if pane.recent_lines else ["(no output)"]
        for line in preview:
            safe = line if line.strip() else "(blank)"
            text += f"  {safe}\n"

        text += (
            f"\n"
            f"  [dim]Window:[/]    {window.window_name} (#{window.window_index})\n"
            f"  [dim]Session:[/]   {session.session_name}\n"
        )
        self._content.update(text)

    def show_window(self, window: WindowInfo, session: SessionInfo) -> None:
        """Display window details."""
        pane_count = len(window.panes)
        text = (
            f"[bold $accent]── Window ──[/]\n"
            f"\n"
            f"  [dim]Name:[/]      {window.window_name}\n"
            f"  [dim]Index:[/]     {window.window_index}\n"
            f"  [dim]ID:[/]        {window.window_id}\n"
            f"  [dim]Active:[/]    {'Yes' if window.is_active else 'No'}\n"
            f"  [dim]Panes:[/]     {pane_count}\n"
            f"\n"
            f"  [dim]Session:[/]   {session.session_name}\n"
        )
        self._content.update(text)

    def show_session(self, session: SessionInfo) -> None:
        """Display session details."""
        window_count = len(session.windows)
        pane_count = sum(len(w.panes) for w in session.windows)
        text = (
            f"[bold $accent]── Session ──[/]\n"
            f"\n"
            f"  [dim]Name:[/]      {session.session_name}\n"
            f"  [dim]ID:[/]        {session.session_id}\n"
            f"  [dim]Attached:[/]  {'Yes' if session.is_attached else 'No'}\n"
            f"  [dim]Windows:[/]   {window_count}\n"
            f"  [dim]Panes:[/]     {pane_count}\n"
        )
        self._content.update(text)

    def clear_detail(self) -> None:
        """Clear the detail panel."""
        self._content.update("Select a node to see details")
