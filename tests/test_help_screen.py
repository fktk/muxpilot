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


@pytest.mark.asyncio
async def test_help_screen_bindings_match_actual():
    app = _TestApp()
    screen = HelpScreen()
    async with app.run_test() as pilot:
        app.push_screen(screen)
        await pilot.pause()
        table = screen.query_one("#help-content")
        keys = [str(table.get_cell_at((row, 0))) for row in range(table.row_count)]

        # Keys that should NOT appear in help (not bound in app)
        for key_cell in keys:
            assert "r" not in key_cell.split(" / "), f"Unexpected 'r' in help keys: {key_cell}"
            assert "e" not in key_cell.split(" / "), f"Unexpected 'e' in help keys: {key_cell}"
            assert "w" not in key_cell.split(" / "), f"Unexpected 'w' in help keys: {key_cell}"
            assert "c" not in key_cell.split(" / "), f"Unexpected 'c' in help keys: {key_cell}"

        # Keys that SHOULD appear in help
        assert any("a" in k for k in keys), "Expected 'a' key in help"
        assert any("?" in k for k in keys), "Expected '?' key in help"
        assert any("q" in k for k in keys), "Expected 'q' key in help"
        assert any("n" in k for k in keys), "Expected 'n' key in help"
        assert any("x" in k for k in keys), "Expected 'x' key in help"
        assert any("/" in k for k in keys), "Expected '/' key in help"
