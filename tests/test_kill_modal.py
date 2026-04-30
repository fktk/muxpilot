import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static

from muxpilot.screens.kill_modal import KillPaneModalScreen


class _TestApp(App[None]):
    def compose(self) -> ComposeResult:
        yield Static("test")


@pytest.mark.asyncio
async def test_kill_modal_confirms_with_y():
    result = []
    def callback(confirmed: bool | None) -> None:
        result.append(confirmed)

    app = _TestApp()
    screen = KillPaneModalScreen("%0", pane_label="Test Pane")
    async with app.run_test() as pilot:
        app.push_screen(screen, callback)
        await pilot.press("y")
        assert result == [True]


@pytest.mark.asyncio
async def test_kill_modal_confirms_with_enter():
    result = []
    def callback(confirmed: bool | None) -> None:
        result.append(confirmed)

    app = _TestApp()
    screen = KillPaneModalScreen("%0")
    async with app.run_test() as pilot:
        app.push_screen(screen, callback)
        screen.focus()  # defocus button so Enter hits screen-level on_key
        await pilot.press("enter")
        assert result == [True]


@pytest.mark.asyncio
async def test_kill_modal_cancels_with_n():
    result = []
    def callback(confirmed: bool | None) -> None:
        result.append(confirmed)

    app = _TestApp()
    screen = KillPaneModalScreen("%0")
    async with app.run_test() as pilot:
        app.push_screen(screen, callback)
        await pilot.press("n")
        assert result == [False]


@pytest.mark.asyncio
async def test_kill_modal_cancels_with_escape():
    result = []
    def callback(confirmed: bool | None) -> None:
        result.append(confirmed)

    app = _TestApp()
    screen = KillPaneModalScreen("%0")
    async with app.run_test() as pilot:
        app.push_screen(screen, callback)
        await pilot.press("escape")
        assert result == [False]


@pytest.mark.asyncio
async def test_kill_modal_shows_pane_label():
    app = _TestApp()
    screen = KillPaneModalScreen("%0", pane_label="My Pane")
    async with app.run_test() as pilot:
        app.push_screen(screen)
        await pilot.pause()
        statics = list(screen.query(".pane-id"))
        assert any("My Pane" in str(s.render()) for s in statics)
