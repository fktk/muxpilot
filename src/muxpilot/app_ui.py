"""UI orchestration helpers for MuxpilotApp."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from muxpilot.models import PaneInfo, SessionInfo, TmuxEvent, TmuxTree, WindowInfo
from muxpilot.widgets.detail_panel import DetailPanel
from muxpilot.widgets.filter_bar import FilterBar
from muxpilot.widgets.tree_view import TmuxTreeView

if TYPE_CHECKING:
    from muxpilot.app import MuxpilotApp


class UIOrchestrator:
    """Handles polling results, UI updates, and detail panel rendering."""

    def __init__(self, app: MuxpilotApp) -> None:
        self._app = app

    def apply_labels(self, tree: TmuxTree) -> None:
        """Apply in-memory overlay labels to the tree snapshot."""
        self._app._rename_controller.apply(tree)

    async def do_refresh(self) -> None:
        """Fetch tmux tree and update the UI."""
        try:
            tree, events = await asyncio.to_thread(self._app._watcher.poll)
        except Exception as e:
            self._app._notify_channel.send(f"Error fetching tmux info: {e}")
            return

        await self.update_ui_from_poll(tree, events, rebuild_tree=True)

    async def handle_poll_result(self, tree: TmuxTree, events: list[TmuxEvent]) -> None:
        """Callback passed to TimerCoordinator for each successful poll."""
        await self.update_ui_from_poll(tree, events, rebuild_tree=True)

    async def poll_tmux(self) -> None:
        """Backward-compatible alias for the periodic polling callback."""
        result = await self._app._polling.tick()
        if result is None:
            return
        tree, events = result
        await self.update_ui_from_poll(tree, events, rebuild_tree=True)

    async def update_ui_from_poll(
        self,
        tree: TmuxTree,
        events: list,
        *,
        rebuild_tree: bool = True,
    ) -> None:
        """Apply labels and update all UI widgets from a poll result."""
        self.apply_labels(tree)

        if rebuild_tree:
            tree_widget = self._app.query_one("#tmux-tree", TmuxTreeView)
            tree_widget.populate(
                tree,
                current_pane_id=self._app._current_pane_id,
                status_filter=self._app._filter_state.status_filter,
                name_filter=self._app._filter_state.name_filter,
            )

            filter_bar = self._app.query_one("#filter-bar", FilterBar)
            filter_bar.update(self._app._filter_state.status_filter, self._app._filter_state.name_filter)

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
        detail = self._app.query_one("#detail-panel", DetailPanel)
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
        if pane_id == self._app._current_pane_id:
            return

        success = self._app._client.navigate_to(pane_id)
        if success:
            self._app._polling.trigger_cooldown()
            await self.do_refresh()

    def check_notifications(self) -> None:
        """Consume messages from NotifyChannel and display as Textual notifications."""
        while True:
            msg = self._app._notify_channel.receive()
            if msg is None:
                break
            event = self._app._watcher.process_notification(msg)
            if event:
                # Refresh UI to reflect the status change
                if self._app._watcher._last_tree is not None:
                    self.apply_labels(self._app._watcher._last_tree)
                    for pane in self._app._watcher._last_tree.all_panes():
                        if pane.pane_id == event.pane_id:
                            pane.status = event.new_status
                            break
                    tree_widget = self._app.query_one("#tmux-tree", TmuxTreeView)
                    tree_widget.populate(
                        self._app._watcher._last_tree,
                        current_pane_id=self._app._current_pane_id,
                        status_filter=self._app._filter_state.status_filter,
                        name_filter=self._app._filter_state.name_filter,
                    )
                self._app.notify(
                    f"{event.pane_id} → {event.new_status.value}", timeout=3
                )
            else:
                self._app.notify(msg, timeout=5)
