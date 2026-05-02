from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static


class HelpScreen(ModalScreen[None]):
    """Full keybinding help modal."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    HelpScreen > Vertical {
        width: 60;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        border: thick $background 80%;
        background: $surface;
    }
    HelpScreen .title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    HelpScreen DataTable {
        height: auto;
        max-height: 1fr;
        border: none;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("muxpilot Help", classes="title")
            table = DataTable(id="help-content")
            table.add_columns("Key", "Action")
            table.add_rows([
                ("↑ / k", "Move cursor up"),
                ("↓ / j", "Move cursor down"),
                ("Enter", "Jump to selected pane"),
                ("/", "Toggle name filter"),
                ("a", "Show all / Clear filters"),
                ("n", "Rename selected node"),
                ("x", "Kill selected pane"),
                ("?", "Show this help"),
                ("q", "Quit"),
            ])
            yield table
            yield Static("Press Esc to close", classes="footer")

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss()
            event.stop()
