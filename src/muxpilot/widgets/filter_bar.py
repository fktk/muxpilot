from __future__ import annotations

from textual.widgets import Static

from muxpilot.models import PaneStatus, STATUS_ICONS


class FilterBar(Static):
    """Shows currently active filters above the tree."""

    DEFAULT_CSS = """
    FilterBar {
        dock: top;
        display: none;
        height: 1;
        background: $warning-darken-2;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }
    FilterBar.-active {
        display: block;
    }
    """

    def update(self, status_filter: set[PaneStatus] | None, name_filter: str) -> None:
        parts: list[str] = []
        if name_filter:
            parts.append(f'name: "{name_filter}"')
        if status_filter:
            labels = []
            for s in status_filter:
                icon = STATUS_ICONS.get(s, "")
                labels.append(f"{icon} {s.value}")
            parts.append("  ".join(labels))
        if parts:
            super().update("Filters: " + "  │  ".join(parts))
            self.add_class("-active")
        else:
            super().update("")
            self.remove_class("-active")
