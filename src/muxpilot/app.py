"""Main Textual application for muxpilot."""

from __future__ import annotations

import asyncio
import sys

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static, Input

from muxpilot.models import TmuxTree, PaneStatus
from muxpilot.notify_channel import NotifyChannel
from muxpilot.tmux_client import TmuxClient
from muxpilot.watcher import TmuxWatcher
from muxpilot.widgets.detail_panel import DetailPanel
from muxpilot.widgets.status_bar import StatusBar
from muxpilot.widgets.tree_view import TmuxTreeView


POLL_INTERVAL_SECONDS = 2.0
NOTIFY_CHECK_INTERVAL = 0.5


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

    #filter-input {
        dock: top;
        display: none;
        margin-bottom: 1;
    }

    #filter-input.-active {
        display: block;
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
        self._status_filter: set[PaneStatus] | None = None
        self._name_filter: str = ""
        self._notify_channel = NotifyChannel()

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            with Vertical(id="tree-panel"):
                yield Input(placeholder="Filter by name...", id="filter-input")
                yield TmuxTreeView(id="tmux-tree")
            yield DetailPanel(id="detail-panel")
        yield StatusBar(id="status-bar")
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize the app after mounting."""
        if not self._client.is_inside_tmux():
            # Still allow running for development, but show a warning
            pass

        self._current_pane_id = self._client.get_current_pane_id()
        await self._do_refresh()

        # Start the polling timer
        self.set_interval(POLL_INTERVAL_SECONDS, self._poll_tmux)

        # Set initial focus to the tree to avoid the hidden input capturing keys
        self.query_one("#tmux-tree").focus()

        await self._notify_channel.start()
        self.set_interval(NOTIFY_CHECK_INTERVAL, self._check_notifications)

    async def _do_refresh(self) -> None:
        """Fetch tmux tree and update the UI."""
        try:
            tree, events = await asyncio.to_thread(self._watcher.poll)
        except Exception as e:
            self._notify_channel.send(f"Error fetching tmux info: {e}")
            return

        # Update current pane ID from the tree's active pane
        active_pane = next((p for s in tree.sessions for w in s.windows for p in w.panes if p.is_active), None)
        if active_pane:
            self._current_pane_id = active_pane.pane_id

        # Update tree view
        tree_widget = self.query_one("#tmux-tree", TmuxTreeView)
        tree_widget.populate(
            tree,
            current_pane_id=self._current_pane_id,
            status_filter=self._status_filter,
            name_filter=self._name_filter
        )
        
        # Update status bar
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.update_stats(tree)

        # Show events as notifications
        for event in events:
            status_bar.show_event(event)
            self._notify_channel.send(event.message)

    async def _poll_tmux(self) -> None:
        """Periodic polling callback."""
        try:
            tree, events = await asyncio.to_thread(self._watcher.poll)
        except Exception:
            return

        # Update status bar
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.update_stats(tree)

        # Only rebuild tree if structure changed
        if events:
            tree_widget = self.query_one("#tmux-tree", TmuxTreeView)
            tree_widget.populate(
                tree,
                current_pane_id=self._current_pane_id,
                status_filter=self._status_filter,
                name_filter=self._name_filter
            )

            for event in events:
                status_bar.show_event(event)
                self._notify_channel.send(event.message)

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
        """Handle pane activation (Enter) → navigate to the pane."""
        pane_id = message.pane_id

        # Don't navigate to our own pane
        if pane_id == self._current_pane_id:
            self._notify_channel.send("This is the current pane")
            return

        success = self._client.navigate_to(pane_id)
        if success:
            # We should NOT use asyncio.create_task here because this method is not an async function
            # and we are not in an async context where create_task is appropriate without a loop.
            # Instead, we can use self.call_later or just rely on the polling.
            # But since we want it immediate, let's use self.set_interval or just trigger refresh.
            self._notify_channel.send(f"Navigated to {pane_id}")
            asyncio.run_coroutine_threadsafe(self._do_refresh(), asyncio.get_event_loop())
        else:
            self._notify_channel.send(f"Failed to navigate to {pane_id}")

    async def action_refresh(self) -> None:
        """Manual refresh (r key)."""
        await self._do_refresh()
        self._notify_channel.send("Refreshed")

    def action_help(self) -> None:
        """Show help (? key)."""
        self._notify_channel.send("j/k: Navigate  Enter: Go to pane  r: Refresh  /: Filter  e: Errors  w: Waiting  a: All  q: Quit")

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Handle filter input changes."""
        if event.input.id == "filter-input":
            self._name_filter = event.value
            await self._do_refresh()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in filter input."""
        if event.input.id == "filter-input":
            # Return focus to tree
            self.query_one("#tmux-tree").focus()

    def action_filter(self) -> None:
        """Open filter input (/ key)."""
        filter_input = self.query_one("#filter-input", Input)
        if filter_input.has_class("-active"):
            filter_input.remove_class("-active")
            filter_input.value = ""
            self.query_one("#tmux-tree").focus()
        else:
            filter_input.add_class("-active")
            filter_input.focus()

    async def action_filter_errors(self) -> None:
        """Filter to show only error panes (e key)."""
        if self._status_filter == {PaneStatus.ERROR}:
            self._status_filter = None
            self._notify_channel.send("Error filter removed")
        else:
            self._status_filter = {PaneStatus.ERROR}
            self._notify_channel.send("Filtering by errors")
        await self._do_refresh()

    async def action_filter_waiting(self) -> None:
        """Filter to show only waiting panes (w key)."""
        if self._status_filter == {PaneStatus.WAITING_INPUT}:
            self._status_filter = None
            self._notify_channel.send("Waiting filter removed")
        else:
            self._status_filter = {PaneStatus.WAITING_INPUT}
            self._notify_channel.send("Filtering by waiting")
        await self._do_refresh()

    async def action_filter_all(self) -> None:
        """Clear all filters (a key)."""
        self._status_filter = None
        self._name_filter = ""
        filter_input = self.query_one("#filter-input", Input)
        filter_input.value = ""
        filter_input.remove_class("-active")
        self._notify_channel.send("All filters cleared")
        await self._do_refresh()

    async def _check_notifications(self) -> None:
        """Consume messages from NotifyChannel and display as Textual notifications."""
        while True:
            msg = self._notify_channel.receive()
            if msg is None:
                break
            self.notify(msg, timeout=5)

    async def on_unmount(self) -> None:
        """Clean up NotifyChannel on app exit."""
        await self._notify_channel.stop()


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
