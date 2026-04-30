"""Tests for the HelpScreen modal."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static

from muxpilot.screens.help_screen import HelpScreen


class _TestApp(App[None]):
    def compose(self) -> ComposeResult:
        yield Static("test")


@pytest.mark.asyncio
async def test_help_screen_shows_bindings():
    app = _TestApp()
    screen = HelpScreen()
    async with app.run_test() as pilot:
        app.push_screen(screen)
        await pilot.pause()
        table = screen.query_one("#help-content")
        # Check that "Enter" appears somewhere in the table
        assert "Enter" in str(table.get_cell_at((0, 0))) or "Enter" in str(table.get_cell_at((0, 1))) or any(
            "Enter" in str(table.get_cell_at((row, 0))) or "Enter" in str(table.get_cell_at((row, 1)))
            for row in range(table.row_count)
        )
