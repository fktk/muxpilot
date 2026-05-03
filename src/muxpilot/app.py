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

from muxpilot.controllers import FilterState, PaneTitleManager
from muxpilot.label_store import LabelStore
from muxpilot.timer_coordinator import TimerCoordinator
from muxpilot.models import PaneInfo, PaneStatus, SessionInfo, TmuxTree, WindowInfo
from muxpilot.notify_channel import NotifyChannel
from muxpilot.screens.help_screen import HelpScreen
from muxpilot.screens.kill_modal import KillPaneModalScreen
from muxpilot.tmux_client import TmuxClient
from muxpilot.watcher import TmuxWatcher
from muxpilot.widgets.detail_panel import DetailPanel
from muxpilot.widgets.filter_bar import FilterBar
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
        width: 1fr;
        border-right: solid $primary-background-lighten-2;
        padding: 0 1;
    }

    #detail-panel {
        width: 1fr;
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
        self._rename_controller = PaneTitleManager(self._client)
        self._polling = TimerCoordinator(
            watcher=self._watcher_instance,
            on_tick=self._handle_poll_result,
            notify_channel=self._notify_channel_instance,
            set_interval=self.set_interval,
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
            self._polling = TimerCoordinator(
                watcher=value,
                on_tick=self._handle_poll_result,
                notify_channel=self._notify_channel_instance,
                set_interval=self.set_interval,
            )

    @property
    def _notify_channel(self):
        return self._notify_channel_instance

    @_notify_channel.setter
    def _notify_channel(self, value) -> None:
        self._notify_channel_instance = value
        if hasattr(self, "_polling"):
            self._polling = TimerCoordinator(
                watcher=self._watcher_instance,
                on_tick=self._handle_poll_result,
                notify_channel=value,
                set_interval=self.set_interval,
            )

    @property
    def _label_store(self):
        return self._label_store_instance

    @_label_store.setter
    def _label_store(self, value) -> None:
        self._label_store_instance = value



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

        # Apply tree panel max-width from config
        tree_panel = self.query_one("#tree-panel", Vertical)
        tree_panel.styles.max_width = self._label_store_instance.get_tree_panel_max_width()

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

    async def _handle_poll_result(self, tree: TmuxTree, events: list[TmuxEvent]) -> None:
        """Callback passed to TimerCoordinator for each successful poll."""
        await self._update_ui_from_poll(tree, events, rebuild_tree=True)

    async def _poll_tmux(self) -> None:
        """Backward-compatible alias for the periodic polling callback."""
        result = await self._polling.tick()
        if result is None:
            return
        tree, events = result
        await self._update_ui_from_poll(tree, events, rebuild_tree=True)

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
                status_filter=self._filter_state.status_filter,
                name_filter=self._filter_state.name_filter,
            )

            filter_bar = self.query_one("#filter-bar", FilterBar)
            filter_bar.update(self._filter_state.status_filter, self._filter_state.name_filter)

    def on_tmux_tree_view_node_info(self, message: TmuxTreeView.NodeInfo) -> None:
        """Handle node highlight → update detail panel."""
        self._update_detail_panel(
            message.node_type,
            message.session_info,
            message.window_info,
            message.pane_info,
        )

    def _update_detail_panel(
        self,
        node_type: str,
        session: SessionInfo | None,
        window: WindowInfo | None,
        pane: PaneInfo | None,
    ) -> None:
        """Update the detail panel for the given node data."""
        detail = self.query_one("#detail-panel", DetailPanel)
        if node_type == "pane" and pane and window and session:
            detail.show_pane(pane, window, session)
        elif node_type == "window" and window and session:
            detail.show_window(window, session)
        elif node_type == "session" and session:
            detail.show_session(session)

    async def on_tmux_tree_view_pane_activated(self, message: TmuxTreeView.PaneActivated) -> None:
        """Handle pane activation (Enter) → navigate to the pane."""
        pane_id = message.pane_id

        # Don't navigate to our own pane
        if pane_id == self._current_pane_id:
            return

        success = self._client.navigate_to(pane_id)
        if success:
            self._polling.trigger_cooldown()
            await self._do_refresh()
        else:
            pass

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
            self._filter_state = self._filter_state.with_name(event.value)
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
        self._filter_state = self._filter_state.cleared()
        filter_input = self.query_one("#filter-input", Input)
        filter_input.value = ""
        filter_input.remove_class("-active")
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
            return

        label = pane.custom_label or pane.pane_id

        def on_result(confirmed: bool | None) -> None:
            if confirmed:
                success = self._client.kill_pane(pane.pane_id)
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
            self._filter_state = self._filter_state.with_name("")
            await self._do_refresh()
            self.query_one("#tmux-tree").focus()
            event.prevent_default()
            event.stop()

    def _check_notifications(self) -> None:
        """Consume messages from NotifyChannel and display as Textual notifications."""
        while True:
            msg = self._notify_channel.receive()
            if msg is None:
                break
            event = self._watcher.process_notification(msg)
            if event:
                # Refresh UI to reflect the status change
                if self._watcher._last_tree is not None:
                    self._apply_labels(self._watcher._last_tree)
                    for pane in self._watcher._last_tree.all_panes():
                        if pane.pane_id == event.pane_id:
                            pane.status = event.new_status
                            break
                    tree_widget = self.query_one("#tmux-tree", TmuxTreeView)
                    tree_widget.populate(
                        self._watcher._last_tree,
                        current_pane_id=self._current_pane_id,
                        status_filter=self._filter_state.status_filter,
                        name_filter=self._filter_state.name_filter,
                    )
                self.notify(
                    f"{event.pane_id} → {event.new_status.value}", timeout=3
                )
            else:
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
