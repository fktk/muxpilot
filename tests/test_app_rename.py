"""Tests for pane rename input (n key)."""

from __future__ import annotations


import pytest

from muxpilot.label_store import LabelStore
from muxpilot.widgets.tree_view import TmuxTreeView

from _test_app_common import _patched_app
from conftest import make_pane, make_session, make_tree, make_window


@pytest.mark.asyncio
async def test_rename_key_shows_input(tmp_path):
    """Pressing n should show the rename input."""
    from textual.widgets import Input

    tree = make_tree(sessions=[
        make_session(session_name="work", windows=[
            make_window(window_name="editor", panes=[make_pane(pane_id="%0")])
        ])
    ])
    store = LabelStore(config_path=tmp_path / "config.toml")
    app = _patched_app(tree=tree, label_store=store)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")  # session
        await pilot.press("j")  # window
        await pilot.press("j")  # pane
        await pilot.pause()

        await app.action_rename()
        await pilot.pause()

        ri = app.query_one("#rename-input", Input)
        assert ri.has_class("-active")


@pytest.mark.asyncio
async def test_rename_submit_sets_pane_title():
    """Submitting a name in rename input should call set_pane_title on the client."""
    from textual.widgets import Input

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause()

        await app.action_rename()
        await pilot.pause()

        ri = app.query_one("#rename-input", Input)
        ri.value = "my test runner"
        await pilot.press("enter")
        await pilot.pause()

        app._client.set_pane_title.assert_called_with("%0", "my test runner")


@pytest.mark.asyncio
async def test_rename_empty_sets_empty_pane_title():
    """Submitting empty string should call set_pane_title with empty string."""
    from textual.widgets import Input

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause()

        await app.action_rename()
        await pilot.pause()

        ri = app.query_one("#rename-input", Input)
        ri.value = ""
        await pilot.press("enter")
        await pilot.pause()

        app._client.set_pane_title.assert_called_with("%0", "")


@pytest.mark.asyncio
async def test_rename_escape_cancels():
    """Pressing Escape during rename should cancel without calling set_pane_title."""
    from textual.widgets import Input

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause()

        await app.action_rename()
        await pilot.pause()

        ri = app.query_one("#rename-input", Input)
        ri.value = "should not save"
        await pilot.press("escape")
        await pilot.pause()

        app._client.set_pane_title.assert_not_called()
        assert not ri.has_class("-active")


@pytest.mark.asyncio
async def test_rename_window_key_shows_input():
    """Pressing n on a window node should show the rename input with window name."""
    from textual.widgets import Input

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")  # session
        await pilot.press("j")  # window
        await pilot.pause()

        await app.action_rename()
        await pilot.pause()

        ri = app.query_one("#rename-input", Input)
        assert ri.has_class("-active")
        assert ri.value == "editor"


@pytest.mark.asyncio
async def test_rename_window_submit_calls_rename_window():
    """Submitting a name for window should call rename_window on the client."""
    from textual.widgets import Input

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, window_id="@0", panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause()

        await app.action_rename()
        await pilot.pause()

        ri = app.query_one("#rename-input", Input)
        ri.value = "new-editor"
        await pilot.press("enter")
        await pilot.pause()

        app._client.rename_window.assert_called_once_with("@0", "new-editor")


@pytest.mark.asyncio
async def test_rename_session_key_shows_input():
    """Pressing n on a session node should show the rename input with session name."""
    from textual.widgets import Input

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")  # session
        await pilot.pause()

        await app.action_rename()
        await pilot.pause()

        ri = app.query_one("#rename-input", Input)
        assert ri.has_class("-active")
        assert ri.value == "work"


@pytest.mark.asyncio
async def test_rename_session_submit_calls_rename_session():
    """Submitting a name for session should call rename_session on the client."""
    from textual.widgets import Input

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")
        await pilot.pause()

        await app.action_rename()
        await pilot.pause()

        ri = app.query_one("#rename-input", Input)
        ri.value = "new-work"
        await pilot.press("enter")
        await pilot.pause()

        app._client.rename_session.assert_called_once_with("$0", "new-work")


@pytest.mark.asyncio
async def test_rename_session_empty_ignored():
    """Submitting empty string for session should NOT call rename_session."""
    from textual.widgets import Input

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")
        await pilot.pause()

        await app.action_rename()
        await pilot.pause()

        ri = app.query_one("#rename-input", Input)
        ri.value = ""
        await pilot.press("enter")
        await pilot.pause()

        app._client.rename_session.assert_not_called()


