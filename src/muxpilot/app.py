"""Main Textual application for muxpilot."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input

from muxpilot.app_actions import ActionHandler
from muxpilot.app_ui import UIOrchestrator
from muxpilot.controllers import FilterState, NodeRenameManager
from muxpilot.label_store import LabelStore
from muxpilot.logging_config import setup_logging
from muxpilot.timer_coordinator import TimerCoordinator
from muxpilot.notify_channel import NotifyChannel
from muxpilot.tmux_client import TmuxClient
from muxpilot.watcher import TmuxWatcher
from muxpilot.widgets.detail_panel import DetailPanel
from muxpilot.widgets.filter_bar import FilterBar
from muxpilot.widgets.tree_view import TmuxTreeView


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
        self._rename_controller = NodeRenameManager(self._client)
        self._ui = UIOrchestrator(self)
        self._actions = ActionHandler(self)
        self._polling = TimerCoordinator(
            watcher=self._watcher_instance,
            on_tick=self._ui.handle_poll_result,
            notify_channel=self._notify_channel_instance,
            set_interval=self.set_interval,
        )
        self.theme = self._label_store_instance.get_theme()

    # --- managed properties that recreate controllers on change ---
    @property
    def _watcher(self):
        return self._watcher_instance

    @_watcher.setter
    def _watcher(self, value: TmuxWatcher) -> None:
        self._watcher_instance = value
        if hasattr(self, "_polling"):
            self._polling = TimerCoordinator(
                watcher=value,
                on_tick=self._ui.handle_poll_result,
                notify_channel=self._notify_channel_instance,
                set_interval=self.set_interval,
            )

    @property
    def _notify_channel(self):
        return self._notify_channel_instance

    @_notify_channel.setter
    def _notify_channel(self, value: NotifyChannel) -> None:
        self._notify_channel_instance = value
        if hasattr(self, "_polling"):
            self._polling = TimerCoordinator(
                watcher=self._watcher_instance,
                on_tick=self._ui.handle_poll_result,
                notify_channel=value,
                set_interval=self.set_interval,
            )

    @property
    def _label_store(self):
        return self._label_store_instance

    @_label_store.setter
    def _label_store(self, value: LabelStore) -> None:
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
        await self._ui.do_refresh()

        # Start the polling timer
        self._polling.start()

        # Set initial focus to the tree to avoid the hidden input capturing keys
        self.query_one("#tmux-tree").focus()

        # Apply tree panel max-width from config
        tree_panel = self.query_one("#tree-panel", Vertical)
        tree_panel.styles.max_width = self._label_store_instance.get_tree_panel_max_width()

        await self._notify_channel.start()
        self.set_interval(NOTIFY_CHECK_INTERVAL, self._ui.check_notifications)

    async def _do_refresh(self) -> None:
        await self._ui.do_refresh()

    async def _poll_tmux(self) -> None:
        await self._ui.poll_tmux()

    def on_tmux_tree_view_node_info(self, message: TmuxTreeView.NodeInfo) -> None:
        self._ui.on_tmux_tree_view_node_info(message)

    async def on_tmux_tree_view_pane_activated(self, message: TmuxTreeView.PaneActivated) -> None:
        await self._ui.on_tmux_tree_view_pane_activated(message)

    def action_help(self) -> None:
        self._actions.action_help()

    def action_quit(self) -> None:
        self._actions.action_quit()

    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter-input":
            self._filter_state = self._filter_state.with_name(event.value)
            await self._ui.do_refresh()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "filter-input":
            self.query_one("#tmux-tree").focus()
        elif event.input.id == "rename-input":
            await self._actions.finish_rename(event.value)

    def action_filter(self) -> None:
        self._actions.action_filter()

    async def action_filter_all(self) -> None:
        await self._actions.action_filter_all()

    async def action_rename(self) -> None:
        await self._actions.action_rename()

    async def _finish_rename(self, value: str) -> None:
        await self._actions.finish_rename(value)

    def _cancel_rename(self) -> None:
        self._actions.cancel_rename()

    def action_kill_pane(self) -> None:
        self._actions.action_kill_pane()

    async def on_key(self, event) -> None:
        rename_input = self.query_one("#rename-input", Input)
        if event.key == "escape" and rename_input.has_class("-active"):
            self._actions.cancel_rename()
            event.prevent_default()
            event.stop()
            return

        filter_input = self.query_one("#filter-input", Input)
        if event.key == "escape" and filter_input.has_class("-active"):
            filter_input.remove_class("-active")
            filter_input.value = ""
            self._filter_state = self._filter_state.with_name("")
            await self._ui.do_refresh()
            self.query_one("#tmux-tree").focus()
            event.prevent_default()
            event.stop()

    def _check_notifications(self) -> None:
        self._ui.check_notifications()

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
    setup_logging()
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
