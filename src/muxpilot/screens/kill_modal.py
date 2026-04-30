from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class KillPaneModalScreen(ModalScreen[bool]):
    """Modal dialog to confirm pane kill."""

    DEFAULT_CSS = """
    KillPaneModalScreen {
        align: center middle;
    }
    KillPaneModalScreen > Vertical {
        width: auto;
        height: auto;
        padding: 1 2;
        border: thick $background 80%;
        background: $surface;
    }
    KillPaneModalScreen .title {
        text-align: center;
        text-style: bold;
        color: $error;
        margin-bottom: 1;
    }
    KillPaneModalScreen .pane-id {
        text-align: center;
        margin-bottom: 1;
    }
    KillPaneModalScreen Horizontal {
        width: auto;
        height: auto;
        align: center middle;
    }
    KillPaneModalScreen Button {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        pane_id: str,
        pane_label: str = "",
    ) -> None:
        super().__init__()
        self.pane_id = pane_id
        self.pane_label = pane_label or pane_id

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Kill Pane?", classes="title")
            yield Static(self.pane_label, classes="pane-id")
            with Horizontal():
                yield Button("Kill (y)", variant="error", id="confirm")
                yield Button("Cancel (n)", variant="primary", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def on_key(self, event: events.Key) -> None:
        if event.key in ("y", "enter"):
            self.dismiss(True)
            event.stop()
        elif event.key in ("n", "escape"):
            self.dismiss(False)
            event.stop()
