"""Tests for app startup, basic UI, and general widget presence."""

from __future__ import annotations

import pathlib

import pytest

from unittest.mock import MagicMock

from muxpilot.screens.help_screen import HelpScreen
from muxpilot.widgets.tree_view import TmuxTreeView

from _test_app_common import _patched_app
from conftest import make_pane, make_session, make_tree, make_window


@pytest.mark.asyncio
async def test_app_launches():
    """App should mount all required widgets without errors."""
    from textual.widgets import Input
    app = _patched_app()
    async with app.run_test():
        assert app.query_one("#tmux-tree", TmuxTreeView) is not None
        assert app.query_one("#detail-panel") is not None
        assert app.query_one("#filter-input", Input) is not None


@pytest.mark.asyncio
async def test_tree_populated_on_mount():
    """Tree should be populated with session/window/pane data on mount."""
    tree = make_tree(sessions=[
        make_session(session_name="test-sess", windows=[
            make_window(window_name="test-win", panes=[make_pane(pane_id="%0")])
        ])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test():
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        assert len(tw._pane_map) > 0


@pytest.mark.asyncio
async def test_tree_panel_max_width_default():
    """Tree panel max-width should default to 60 when no config is set."""
    from textual.containers import Vertical
    from textual.css.scalar import Scalar

    app = _patched_app(config_path=pathlib.Path("/nonexistent-config-for-test"))
    async with app.run_test():
        tree_panel = app.query_one("#tree-panel", Vertical)
        assert tree_panel.styles.max_width == Scalar.parse("60")


@pytest.mark.asyncio
async def test_tree_panel_max_width_from_config(tmp_path):
    """Tree panel max-width should be read from config.toml."""
    from textual.containers import Vertical
    from textual.css.scalar import Scalar

    config_path = tmp_path / "config.toml"
    config_path.write_text('[ui]\ntree_panel_max_width = 80\n')

    app = _patched_app(config_path=config_path)
    async with app.run_test():
        tree_panel = app.query_one("#tree-panel", Vertical)
        assert tree_panel.styles.max_width == Scalar.parse("80")


@pytest.mark.asyncio
async def test_shows_warning_when_not_in_tmux():
    """App should show a warning when launched outside a tmux session."""
    app = _patched_app()
    app._client.is_inside_tmux = MagicMock(return_value=False)
    async with app.run_test() as pilot:
        await pilot.pause(0.1)
        messages = [call.args[0] for call in app._notify_channel.send.call_args_list if call.args]
        assert any("not running inside a tmux session" in m.lower() for m in messages)


# ============================================================================
# Navigation
# ============================================================================


@pytest.mark.asyncio
async def test_quit_key():
    """Pressing q should exit the app."""
    app = _patched_app()
    async with app.run_test() as pilot:
        await pilot.press("q")
    # After context manager exits the app has stopped — just verify no exception


@pytest.mark.asyncio
async def test_help_screen_esc_closes():
    """Pressing Escape while help is open should dismiss the help screen."""
    app = _patched_app()
    async with app.run_test() as pilot:
        app.push_screen(HelpScreen())
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_q_in_help_screen_does_not_quit():
    """Pressing q while help is open should not exit the app."""
    app = _patched_app()
    async with app.run_test() as pilot:
        app.push_screen(HelpScreen())
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("q")
        await pilot.pause()
        # App should still be running and HelpScreen should still be active
        assert isinstance(app.screen, HelpScreen)
        assert app.is_running


# ============================================================================
# Filter: name filter (/ toggle)
# ============================================================================


@pytest.mark.asyncio
async def test_app_notifies_config_error():
    """Watcher に config_error があるとき、NotifyChannel にエラーメッセージが送信されること。"""
    app = _patched_app(config_error="invalid regex")
    async with app.run_test() as pilot:
        await pilot.pause(0.1)
        messages = [call.args[0] for call in app._notify_channel.send.call_args_list if call.args]
        assert any("invalid regex" in m for m in messages)


@pytest.mark.asyncio
async def test_notify_channel_started_on_mount():
    """on_mount で NotifyChannel.start() が呼ばれること。"""
    app = _patched_app()
    async with app.run_test():
        app._notify_channel.start.assert_called_once()


@pytest.mark.asyncio
async def test_detail_panel_hidden_when_below_threshold():
    """Terminal width below threshold should hide detail-panel."""
    from textual.events import Resize
    from textual.geometry import Size

    app = _patched_app()
    async with app.run_test():
        detail = app.query_one("#detail-panel")
        size = Size(70, 24)
        await app.on_resize(Resize(app, size, size))
        assert detail.styles.display == "none"


@pytest.mark.asyncio
async def test_detail_panel_shown_when_above_threshold():
    """Terminal width above threshold should show detail-panel."""
    from textual.events import Resize
    from textual.geometry import Size

    app = _patched_app()
    async with app.run_test():
        detail = app.query_one("#detail-panel")
        small = Size(70, 24)
        large = Size(100, 24)
        await app.on_resize(Resize(app, small, small))
        assert detail.styles.display == "none"
        await app.on_resize(Resize(app, large, large))
        assert detail.styles.display == "block"


@pytest.mark.asyncio
async def test_detail_panel_never_hidden_when_threshold_is_zero(tmp_path):
    """Threshold of 0 should disable auto-hide."""
    from textual.events import Resize
    from textual.geometry import Size

    config_path = tmp_path / "config.toml"
    config_path.write_text('[ui]\nsidebar_hide_threshold = 0\n')
    app = _patched_app(config_path=config_path)
    async with app.run_test():
        detail = app.query_one("#detail-panel")
        size = Size(70, 24)
        await app.on_resize(Resize(app, size, size))
        assert detail.styles.display == "block"


