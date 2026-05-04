"""Detail panel showing information about the selected tree node."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Markdown, RichLog

from muxpilot.models import (
    PaneInfo,
    PaneStatus,
    STATUS_ICONS,
    SessionInfo,
    WindowInfo,
    _shorten_path,
    rich_to_markdown,
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

    DetailPanel Markdown H2 {
        color: $accent;
    }

    #detail-meta {
        height: auto;
        max-height: 60%;
    }

    #detail-output {
        height: 1fr;
        border-top: solid $primary-background-lighten-2;
    }
    """

    def __init__(self, name: str | None = None, id: str | None = None) -> None:
        super().__init__(name=name, id=id)
        self._meta = Markdown("Select a node to see details", id="detail-meta")
        self._log = RichLog(
                id="detail-output", highlight=True, max_lines=35,
                )
        self._markdown_source = ""

    def compose(self) -> ComposeResult:
        yield self._meta
        yield self._log

    def show_pane(self, pane: PaneInfo, window: WindowInfo, session: SessionInfo) -> None:
        """Display pane details."""
        icon = STATUS_ICONS.get(pane.status, "?")
        markdown_icon = rich_to_markdown(icon)
        status_name = pane.status.value if pane.status else "unknown"
        if (pane.idle_seconds > 0 and status_name == "idle"):
            idle_text = f" ({pane.idle_seconds:.1f}s idle)"
        else:
            idle_text = ""
        title = pane.pane_title or "—"
        repo = pane.repo_name or "—"
        branch = pane.branch or "—"

        text = (
            f"## Pane\n\n"
            f"- **Session:** {session.session_name}\n"
            f"- **Window:** {window.window_name} (#{window.window_index})\n"
            f"- **ID:** {pane.pane_id}\n"
            f"- **Title:** {title}\n"
            f"- **Repository:** {repo}\n"
            f"- **Branch:** {branch}\n"
            f"- **Command:** `{pane.full_command or pane.current_command}`\n"
            f"- **Path:** {_shorten_path(pane.current_path)}\n"
            f"- **Status:** {status_name.upper()}{idle_text}\n"
        )

        if pane.status == PaneStatus.ERROR:
            text += "\n> **Status is ERROR**\n"
        elif pane.status == PaneStatus.WAITING_INPUT:
            text += "\n> **Waiting for input**\n"

        self._markdown_source = text
        self._meta.update(text)

        log = self.query_one("#detail-output", RichLog)
        log.clear()
        preview = pane.recent_lines if pane.recent_lines else ["(no output)"]
        for line in preview:
            log.write(line)

    def show_window(self, window: WindowInfo, session: SessionInfo) -> None:
        """Display window details."""
        text = (
            f"## Window\n\n"
            f"- **Session:** {session.session_name}\n"
            f"- **Name:** {window.window_name}\n"
            f"- **Index:** {window.window_index}\n"
            f"- **ID:** {window.window_id}\n"
            f"- **Active:** {'Yes' if window.is_active else 'No'}\n"
        )
        self._markdown_source = text
        self._meta.update(text)
        self.query_one("#detail-output", RichLog).clear()

    def show_session(self, session: SessionInfo) -> None:
        """Display session details."""
        text = (
            f"## Session\n\n"
            f"- **Name:** {session.session_name}\n"
            f"- **ID:** {session.session_id}\n"
            f"- **Attached:** {'Yes' if session.is_attached else 'No'}\n"
        )
        self._markdown_source = text
        self._meta.update(text)
        self.query_one("#detail-output", RichLog).clear()

    def clear_detail(self) -> None:
        """Clear the detail panel."""
        self._markdown_source = "Select a node to see details"
        self._meta.update(self._markdown_source)
        self.query_one("#detail-output", RichLog).clear()
