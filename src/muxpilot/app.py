"""Main Textual application for muxpilot."""

from __future__ import annotations

import asyncio
import os
import pathlib
import subprocess
import sys

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static, Input

from muxpilot.controllers import FilterState, PollingController, RenameController
from muxpilot.label_store import LabelStore
from muxpilot.models import TmuxTree, PaneStatus
from muxpilot.notify_channel import NotifyChannel
from muxpilot.screens.help_screen import HelpScreen
from muxpilot.screens.kill_modal import KillPaneModalScreen
from muxpilot.tmux_client import TmuxClient
from muxpilot.watcher import TmuxWatcher
from muxpilot.widgets.detail_panel import DetailPanel
from muxpilot.widgets.filter_bar import FilterBar
from muxpilot.widgets.status_bar import StatusBar
from muxpilot.widgets.tree_view import TmuxTreeView


MAX_POLL_BACKOFF_SECONDS = 30.0
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

    #rename-input {
        dock: top;
        display: none;
        margin-bottom: 1;
    }

    #rename-input.-active {
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
        Binding("question_mark", "help", "Help", show=False),
        Binding("slash", "filter", "Filter"),
        Binding("a", "filter_all", "Show all"),
        Binding("n", "rename", "Rename"),
        Binding("x", "kill_pane", "Kill pane"),
    ]

    def __init__(self, config_path: pathlib.Path | None = None) -> None:
        super().__init__()
        self._client = TmuxClient()
        self._watcher_instance = TmuxWatcher(self._client)
        self._current_pane_id: str | None = None
        self._navigate_to: str | None = None
        self._notify_channel_instance = NotifyChannel()
        self._label_store_instance = LabelStore(config_path=config_path)
        self._notify_config_error()

        self._filter_state = FilterState()
        self._rename_controller = RenameController(self._client)
        self._polling = PollingController(
            self, self._watcher_instance, self._notify_channel_instance
        )
        self.theme = self._label_store_instance.get_theme()

    # --- managed properties that recreate controllers on change ---
    @property
    def _watcher(self):
        return self._watcher_instance

    @_watcher.setter
    def _watcher(self, value) -> None:
        self._watcher_instance = value
        if hasattr(self, "_polling"):
            self._polling = PollingController(
                self, value, self._notify_channel_instance
            )

    @property
    def _notify_channel(self):
        return self._notify_channel_instance

    @_notify_channel.setter
    def _notify_channel(self, value) -> None:
        self._notify_channel_instance = value
        if hasattr(self, "_polling"):
            self._polling = PollingController(
                self, self._watcher_instance, value
            )

    @property
    def _label_store(self):
        return self._label_store_instance

    @_label_store.setter
    def _label_store(self, value) -> None:
        self._label_store_instance = value

    # --- backward-compatible property delegates for tests ---
    @property
    def _status_filter(self) -> set[PaneStatus] | None:
        return self._filter_state.status_filter

    @_status_filter.setter
    def _status_filter(self, value: set[PaneStatus] | None) -> None:
        self._filter_state.status_filter = value

    @property
    def _name_filter(self) -> str:
        return self._filter_state.name_filter

    @_name_filter.setter
    def _name_filter(self, value: str) -> None:
        self._filter_state.name_filter = value

    @property
    def _rename_key(self) -> str | None:
        return self._rename_controller.key

    @_rename_key.setter
    def _rename_key(self, value: str | None) -> None:
        self._rename_controller.key = value

    @property
    def _poll_backoff(self) -> float:
        return self._polling.backoff

    @_poll_backoff.setter
    def _poll_backoff(self, value: float) -> None:
        self._polling.backoff = value

    @property
    def _poll_timer(self):
        return self._polling.poll_timer

    @_poll_timer.setter
    def _poll_timer(self, value) -> None:
        self._polling.poll_timer = value

    @property
    def _retry_timer(self):
        return self._polling.retry_timer

    @_retry_timer.setter
    def _retry_timer(self, value) -> None:
        self._polling.retry_timer = value

    def watch_theme(self, theme: str) -> None:
        """Save theme to config when it changes."""
        if hasattr(self, "_label_store"):
            self._label_store.set_theme(theme)

    def _notify_config_error(self) -> None:
        """Send config error from watcher to the notify channel."""
        error = self._watcher.config_error
        if error:
            self._notify_channel.send(f"Config error: {error}")

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            with Vertical(id="tree-panel"):
                yield Input(placeholder="Filter by name...", id="filter-input")
                yield Input(placeholder="New name (empty to reset)...", id="rename-input")
                yield FilterBar(id="filter-bar")
                yield TmuxTreeView(id="tmux-tree")
            yield DetailPanel(id="detail-panel")
        yield StatusBar(id="status-bar")
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize the app after mounting."""
        if not self._client.is_inside_tmux():
            # Still allow running for development, but show a warning
            self._notify_channel.send("Warning: not running inside a tmux session")

        self._current_pane_id = self._client.get_current_pane_id()
        await self._do_refresh()

        # Start the polling timer
        self._polling.start()

        # Set initial focus to the tree to avoid the hidden input capturing keys
        self.query_one("#tmux-tree").focus()

        # Apply detail panel width from config
        detail_panel = self.query_one("#detail-panel", DetailPanel)
        detail_panel.styles.width = self._label_store_instance.get_detail_panel_width()

        await self._notify_channel.start()
        self.set_interval(NOTIFY_CHECK_INTERVAL, self._check_notifications)

    def _apply_labels(self, tree: TmuxTree) -> None:
        """Apply in-memory overlay labels to the tree snapshot."""
        self._rename_controller.apply(tree)

    async def _do_refresh(self) -> None:
        """Fetch tmux tree and update the UI."""
        try:
            tree, events = await asyncio.to_thread(self._watcher.poll)
        except Exception as e:
            self._notify_channel.send(f"Error fetching tmux info: {e}")
            return

        await self._update_ui_from_poll(tree, events, rebuild_tree=True)

    async def _poll_tmux(self) -> None:
        """Backward-compatible alias for the periodic polling callback."""
        await self._on_poll_tick()

    async def _on_poll_tick(self) -> None:
        """Periodic polling callback — delegates to PollingController."""
        result = await self._polling.tick()
        if result is None:
            return
        tree, events = result
        await self._update_ui_from_poll(tree, events, rebuild_tree=bool(events))

    async def _update_ui_from_poll(
        self,
        tree: TmuxTree,
        events: list,
        *,
        rebuild_tree: bool = True,
    ) -> None:
        """Apply labels and update all UI widgets from a poll result."""
        self._apply_labels(tree)

        if rebuild_tree:
            tree_widget = self.query_one("#tmux-tree", TmuxTreeView)
            tree_widget.populate(
                tree,
                current_pane_id=self._current_pane_id,
                status_filter=self._status_filter,
                name_filter=self._name_filter,
            )

            filter_bar = self.query_one("#filter-bar", FilterBar)
            filter_bar.update(self._status_filter, self._name_filter)

        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.update_stats(tree)

        for event in events:
            status_bar.show_event(event)
            if event.event_type not in ("status_changed", "focus_changed"):
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

    async def on_tmux_tree_view_pane_activated(self, message: TmuxTreeView.PaneActivated) -> None:
        """Handle pane activation (Enter) → navigate to the pane."""
        pane_id = message.pane_id

        # Don't navigate to our own pane
        if pane_id == self._current_pane_id:
            self._notify_channel.send("This is the current pane")
            return

        success = self._client.navigate_to(pane_id)
        if success:
            self._notify_channel.send(f"Navigated to {pane_id}")
            self._polling.trigger_cooldown()
            await self._do_refresh()
        else:
            self._notify_channel.send(f"Failed to navigate to {pane_id}")

    def action_help(self) -> None:
        """Show help (? key)."""
        self.push_screen(HelpScreen())

    def action_quit(self) -> None:
        """Quit the app, unless the help screen is open."""
        if isinstance(self.screen, HelpScreen):
            return
        self.exit()

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Handle filter input changes."""
        if event.input.id == "filter-input":
            self._name_filter = event.value
            await self._do_refresh()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in filter or rename input."""
        if event.input.id == "filter-input":
            self.query_one("#tmux-tree").focus()
        elif event.input.id == "rename-input":
            await self._finish_rename(event.value)

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

    async def action_filter_all(self) -> None:
        """Clear all filters (a key)."""
        self._filter_state.clear_all()
        filter_input = self.query_one("#filter-input", Input)
        filter_input.value = ""
        filter_input.remove_class("-active")
        self._notify_channel.send("All filters cleared")
        await self._do_refresh()

    async def action_rename(self) -> None:
        """Start renaming the currently selected tree node (n key)."""
        tw = self.query_one("#tmux-tree", TmuxTreeView)
        data = tw.get_cursor_node_data()
        current = self._rename_controller.start(data)
        if current is None:
            return

        rename_input = self.query_one("#rename-input", Input)
        rename_input.value = current
        rename_input.add_class("-active")
        rename_input.focus()

    async def _finish_rename(self, value: str) -> None:
        """Save the rename and close the input."""
        self._rename_controller.finish(value)
        rename_input = self.query_one("#rename-input", Input)
        rename_input.value = ""
        rename_input.remove_class("-active")
        self.query_one("#tmux-tree").focus()
        await self._do_refresh()

    def _cancel_rename(self) -> None:
        """Cancel rename without saving."""
        self._rename_controller.cancel()
        rename_input = self.query_one("#rename-input", Input)
        rename_input.value = ""
        rename_input.remove_class("-active")
        self.query_one("#tmux-tree").focus()

    def action_kill_pane(self) -> None:
        """Show modal to confirm killing the currently selected pane (x key)."""
        tw = self.query_one("#tmux-tree", TmuxTreeView)
        data = tw.get_cursor_node_data()
        if data is None:
            return

        node_type, session, window, pane = data
        if node_type != "pane" or pane is None:
            return

        # Don't kill our own pane
        if pane.pane_id == self._current_pane_id:
            self._notify_channel.send("Cannot kill the current pane")
            return

        label = pane.custom_label or pane.pane_id

        def on_result(confirmed: bool | None) -> None:
            if confirmed:
                success = self._client.kill_pane(pane.pane_id)
                msg = f"Killed pane {label}" if success else f"Failed to kill pane {label}"
                self._notify_channel.send(msg)
                self._polling.trigger_cooldown()
                asyncio.create_task(self._do_refresh())

        self.push_screen(
            KillPaneModalScreen(pane.pane_id, label),
            on_result,
        )

    async def on_key(self, event) -> None:
        """Handle Escape key during rename or filter."""
        rename_input = self.query_one("#rename-input", Input)
        if event.key == "escape" and rename_input.has_class("-active"):
            self._cancel_rename()
            event.prevent_default()
            event.stop()
            return

        filter_input = self.query_one("#filter-input", Input)
        if event.key == "escape" and filter_input.has_class("-active"):
            filter_input.remove_class("-active")
            filter_input.value = ""
            self._name_filter = ""
            await self._do_refresh()
            self.query_one("#tmux-tree").focus()
            event.prevent_default()
            event.stop()

    async def _check_notifications(self) -> None:
        """Consume messages from NotifyChannel and display as Textual notifications."""
        while True:
            msg = self._notify_channel.receive()
            if msg is None:
                break
            self.notify(msg, timeout=5)

    def get_system_commands(self, screen):
        """コマンドパレットから Keys / Screenshot を除外する。"""
        _EXCLUDED = {"Keys", "Screenshot"}
        for command in super().get_system_commands(screen):
            if command.title not in _EXCLUDED:
                yield command

    async def on_unmount(self) -> None:
        """Clean up timers and NotifyChannel on app exit."""
        self._polling.stop()
        await self._notify_channel.stop()


def main() -> None:
    """Entry point for the muxpilot CLI."""
    client = TmuxClient()
    if not client.is_inside_tmux():
        session_name = "muxpilot"
        try:
            subprocess.run(
                ["tmux", "new-session", "-s", session_name, "-d",
                 sys.executable, "-m", "muxpilot"],
                check=True,
            )
        except subprocess.CalledProcessError:
            # Session already exists or another tmux error; just try to attach
            pass
        os.execlp("tmux", "tmux", "attach", "-t", session_name)

    app = MuxpilotApp()
    result = app.run()

    # After the TUI exits, navigate to the selected pane
    if result:
        success = client.navigate_to(result)
        if not success:
            print(f"Failed to navigate to pane {result}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
