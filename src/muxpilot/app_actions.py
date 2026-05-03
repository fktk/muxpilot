"""Action handlers for MuxpilotApp key bindings."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from textual.widgets import Input

from muxpilot.screens.help_screen import HelpScreen
from muxpilot.screens.kill_modal import KillPaneModalScreen
from muxpilot.widgets.tree_view import TmuxTreeView

if TYPE_CHECKING:
    from muxpilot.app import MuxpilotApp


class ActionHandler:
    """Handles key-bound actions and modal interactions."""

    def __init__(self, app: MuxpilotApp) -> None:
        self._app = app

    def action_help(self) -> None:
        """Show help (? key)."""
        self._app.push_screen(HelpScreen())

    def action_quit(self) -> None:
        """Quit the app, unless the help screen is open."""
        if isinstance(self._app.screen, HelpScreen):
            return
        self._app.exit()

    def action_filter(self) -> None:
        """Open filter input (/ key)."""
        filter_input = self._app.query_one("#filter-input", Input)
        if filter_input.has_class("-active"):
            filter_input.remove_class("-active")
            filter_input.value = ""
            self._app.query_one("#tmux-tree").focus()
        else:
            filter_input.add_class("-active")
            filter_input.focus()

    async def action_filter_all(self) -> None:
        """Clear all filters (a key)."""
        self._app._filter_state = self._app._filter_state.cleared()
        filter_input = self._app.query_one("#filter-input", Input)
        filter_input.value = ""
        filter_input.remove_class("-active")
        await self._app._ui.do_refresh()

    async def action_rename(self) -> None:
        """Start renaming the currently selected tree node (n key)."""
        tw = self._app.query_one("#tmux-tree", TmuxTreeView)
        data = tw.get_cursor_node_data()
        current = self._app._rename_controller.start(data)
        if current is None:
            return

        rename_input = self._app.query_one("#rename-input", Input)
        rename_input.value = current
        rename_input.add_class("-active")
        rename_input.focus()

    async def finish_rename(self, value: str) -> None:
        """Save the rename and close the input."""
        self._app._rename_controller.finish(value)
        rename_input = self._app.query_one("#rename-input", Input)
        rename_input.value = ""
        rename_input.remove_class("-active")
        self._app.query_one("#tmux-tree").focus()
        await self._app._ui.do_refresh()

    def cancel_rename(self) -> None:
        """Cancel rename without saving."""
        self._app._rename_controller.cancel()
        rename_input = self._app.query_one("#rename-input", Input)
        rename_input.value = ""
        rename_input.remove_class("-active")
        self._app.query_one("#tmux-tree").focus()

    def action_kill_pane(self) -> None:
        """Show modal to confirm killing the currently selected pane (x key)."""
        tw = self._app.query_one("#tmux-tree", TmuxTreeView)
        data = tw.get_cursor_node_data()
        if data is None:
            return

        node_type, session, window, pane = data
        if node_type != "pane" or pane is None:
            return

        # Don't kill our own pane
        if pane.pane_id == self._app._current_pane_id:
            return

        label = pane.custom_label or pane.pane_id

        def on_result(confirmed: bool | None) -> None:
            if confirmed:
                self._app._client.kill_pane(pane.pane_id)
                self._app._polling.trigger_cooldown()
                asyncio.create_task(self._app._ui.do_refresh())

        self._app.push_screen(
            KillPaneModalScreen(pane.pane_id, label),
            on_result,
        )
