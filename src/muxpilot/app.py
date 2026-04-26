"""Main Textual application for muxpilot."""

from __future__ import annotations

import sys

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static

from muxpilot.models import TmuxTree
from muxpilot.tmux_client import TmuxClient
from muxpilot.watcher import TmuxWatcher
from muxpilot.widgets.detail_panel import DetailPanel
from muxpilot.widgets.status_bar import StatusBar
from muxpilot.widgets.tree_view import TmuxTreeView


POLL_INTERVAL_SECONDS = 2.0


class MuxpilotApp(App[str | None]):
    """TUI application for tmux session/pane navigation and agent orchestration."""

    TITLE = "muxpilot"
    SUB_TITLE = "tmux agent orchestrator"

    CSS = """
    Screen {
        layout: vertical;
    }

    #main-container {
        height: 1fr;
    }

    #tree-panel {
        width: 2fr;
        min-width: 30;
        border-right: solid $primary-background-lighten-2;
        padding: 0 1;
    }

    #detail-panel {
        width: 1fr;
        min-width: 25;
    }

    TmuxTreeView {
        height: 1fr;
    }

    #no-tmux-message {
        width: 100%;
        height: 100%;
        content-align: center middle;
        text-align: center;
        color: $error;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("r", "refresh", "Refresh"),
        Binding("question_mark", "help", "Help"),
        Binding("slash", "filter", "Filter"),
        Binding("e", "filter_errors", "Errors only"),
        Binding("w", "filter_waiting", "Waiting only"),
        Binding("a", "filter_all", "Show all"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._client = TmuxClient()
        self._watcher = TmuxWatcher(self._client)
        self._current_pane_id: str | None = None
        self._navigate_to: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            with Vertical(id="tree-panel"):
                yield TmuxTreeView(id="tmux-tree")
            yield DetailPanel(id="detail-panel")
        yield StatusBar(id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the app after mounting."""
        if not self._client.is_inside_tmux():
            # Still allow running for development, but show a warning
            pass

        self._current_pane_id = self._client.get_current_pane_id()
        self._do_refresh()

        # Start the polling timer
        self.set_interval(POLL_INTERVAL_SECONDS, self._poll_tmux)

    def _do_refresh(self) -> None:
        """Fetch tmux tree and update the UI."""
        try:
            tree, events = self._watcher.poll()
        except Exception as e:
            self.notify(f"Error fetching tmux info: {e}", severity="error")
            return

        # Update tree view
        tree_widget = self.query_one("#tmux-tree", TmuxTreeView)
        tree_widget.populate(tree, self._current_pane_id)

        # Update status bar
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.update_stats(tree)

        # Show events as notifications
        for event in events:
            status_bar.show_event(event)
            self.notify(event.message, timeout=5)

    async def _poll_tmux(self) -> None:
        """Periodic polling callback."""
        try:
            tree, events = self._watcher.poll()
        except Exception:
            return

        # Update status bar
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.update_stats(tree)

        # Only rebuild tree if structure changed
        if events:
            tree_widget = self.query_one("#tmux-tree", TmuxTreeView)
            tree_widget.populate(tree, self._current_pane_id)

            for event in events:
                status_bar.show_event(event)
                self.notify(event.message, timeout=5)

    def on_tmux_tree_view_node_info(self, message: TmuxTreeView.NodeInfo) -> None:
        """Handle node highlight → update detail panel."""
        detail = self.query_one("#detail-panel", DetailPanel)
        if message.node_type == "pane" and message.pane_info and message.window_info and message.session_info:
            detail.show_pane(message.pane_info, message.window_info, message.session_info)
        elif message.node_type == "window" and message.window_info and message.session_info:
            detail.show_window(message.window_info, message.session_info)
        elif message.node_type == "session" and message.session_info:
            detail.show_session(message.session_info)

    def on_tmux_tree_view_pane_activated(self, message: TmuxTreeView.PaneActivated) -> None:
        """Handle pane activation (Enter) → navigate to the pane and exit."""
        pane_id = message.pane_id

        # Don't navigate to our own pane
        if pane_id == self._current_pane_id:
            self.notify("This is the current pane", severity="warning")
            return

        self._navigate_to = pane_id
        self.exit(pane_id)

    def action_refresh(self) -> None:
        """Manual refresh (r key)."""
        self._do_refresh()
        self.notify("Refreshed", timeout=2)

    def action_help(self) -> None:
        """Show help (? key)."""
        self.notify(
            "j/k: Navigate  Enter: Go to pane  r: Refresh  "
            "/: Filter  e: Errors  w: Waiting  a: All  q: Quit",
            timeout=10,
        )

    def action_filter(self) -> None:
        """Open filter input (/ key). Phase 2 stub."""
        self.notify("Filter: coming soon", timeout=2)

    def action_filter_errors(self) -> None:
        """Filter to show only error panes (e key). Phase 2 stub."""
        self.notify("Errors filter: coming soon", timeout=2)

    def action_filter_waiting(self) -> None:
        """Filter to show only waiting panes (w key). Phase 2 stub."""
        self.notify("Waiting filter: coming soon", timeout=2)

    def action_filter_all(self) -> None:
        """Clear all filters (a key). Phase 2 stub."""
        self.notify("All filters cleared", timeout=2)


def main() -> None:
    """Entry point for the muxpilot CLI."""
    app = MuxpilotApp()
    result = app.run()

    # After the TUI exits, navigate to the selected pane
    if result:
        client = TmuxClient()
        success = client.navigate_to(result)
        if not success:
            print(f"Failed to navigate to pane {result}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
