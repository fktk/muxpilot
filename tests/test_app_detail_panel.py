"""Tests for DetailPanel content rendering."""

from __future__ import annotations

import pytest

from muxpilot.models import PaneStatus
from muxpilot.widgets.detail_panel import DetailPanel
from muxpilot.widgets.tree_view import TmuxTreeView
from textual.widgets import Markdown, RichLog

from _test_app_common import _patched_app
from conftest import make_pane, make_session, make_tree, make_window


def _run_detail_panel(panel):
    """Wrap a DetailPanel in a minimal App and run it in a test context."""
    from textual.app import App
    from textual.app import ComposeResult

    class _TestApp(App):
        def compose(self) -> ComposeResult:
            yield panel

    return _TestApp()


@pytest.mark.asyncio
async def test_detail_panel_composes_markdown_and_richlog():
    """DetailPanel should contain a Markdown and a RichLog widget."""
    panel = DetailPanel()
    app = _run_detail_panel(panel)
    async with app.run_test():
        meta = panel.query_one("#detail-meta", Markdown)
        log = panel.query_one("#detail-output", RichLog)
        assert meta is not None
        assert log is not None


@pytest.mark.asyncio
async def test_detail_panel_shows_pane_title_and_git():
    """Detail panel should display pane title, repo, branch, and idle time."""
    panel = DetailPanel()
    session = make_session(session_name="dev", windows=[
        make_window(window_name="editor", panes=[
            make_pane(
                pane_id="%0",
                pane_title="agent-a",
                repo_name="proj",
                branch="feat/x",
                idle_seconds=12.0,
                status=PaneStatus.IDLE,
                recent_lines=["line1", "line2"],
            )
        ])
    ])
    window = session.windows[0]
    pane = window.panes[0]
    app = _run_detail_panel(panel)
    async with app.run_test():
        panel.show_pane(pane, window, session)
        text = panel._markdown_source
        assert "agent-a" in text
        assert "proj" in text
        assert "feat/x" in text
        assert "12.0s idle" in text
        assert "line1" not in text
        assert "line2" not in text

        log = panel.query_one("#detail-output", RichLog)
        lines = log.lines
        assert any("line1" in str(line) for line in lines)
        assert any("line2" in str(line) for line in lines)


@pytest.mark.asyncio
async def test_detail_panel_shows_pane_meta_in_markdown_and_output_in_richlog():
    """show_pane should put meta in Markdown and recent_lines in RichLog."""
    panel = DetailPanel()
    session = make_session(session_name="dev", windows=[
        make_window(window_name="editor", panes=[
            make_pane(
                pane_id="%0",
                pane_title="agent-a",
                repo_name="proj",
                branch="feat/x",
                idle_seconds=12.0,
                status=PaneStatus.IDLE,
                recent_lines=["line1", "line2"],
            )
        ])
    ])
    window = session.windows[0]
    pane = window.panes[0]
    app = _run_detail_panel(panel)
    async with app.run_test():
        panel.show_pane(pane, window, session)
        # Markdown should contain meta, not output section
        assert "agent-a" in panel._markdown_source
        assert "proj" in panel._markdown_source
        assert "feat/x" in panel._markdown_source
        assert "12.0s idle" in panel._markdown_source
        assert "## Recent Output" not in panel._markdown_source
        assert "line1" not in panel._markdown_source

        # RichLog should contain output lines
        log = panel.query_one("#detail-output", RichLog)
        lines = log.lines
        assert any("line1" in str(line) for line in lines)
        assert any("line2" in str(line) for line in lines)


@pytest.mark.asyncio
async def test_detail_panel_error_status_shows_clean_icon():
    """Detail panel should render ERROR status icon cleanly without broken markup."""
    panel = DetailPanel()
    session = make_session(session_name="dev", windows=[
        make_window(window_name="editor", panes=[
            make_pane(pane_id="%0", status=PaneStatus.ERROR)
        ])
    ])
    window = session.windows[0]
    pane = window.panes[0]
    app = _run_detail_panel(panel)
    async with app.run_test():
        panel.show_pane(pane, window, session)
        text = panel._markdown_source

        # Should NOT contain broken/unclosed markup fragments
        assert "[bold" not in text, f"Broken bold markup found: {text}"
        assert "red]" not in text, f"Broken red markup found: {text}"
        # Should show the bold letter E in Markdown
        assert "**E**" in text, f"Bold E not found in status line: {text}"
        assert "error" in text


@pytest.mark.asyncio
async def test_detail_panel_pane_shows_session_and_window_before_title():
    """Pane details should show Session and Window before Title, and not repeat them in output."""
    panel = DetailPanel()
    session = make_session(session_name="my-session", windows=[
        make_window(window_name="my-window", window_index=3, panes=[
            make_pane(pane_id="%0", pane_title="agent-a", recent_lines=["line1"])
        ])
    ])
    window = session.windows[0]
    pane = window.panes[0]
    app = _run_detail_panel(panel)
    async with app.run_test():
        panel.show_pane(pane, window, session)
        text = panel._markdown_source

        pane_section_start = text.find("## Pane")
        assert pane_section_start != -1
        assert "## Recent Output" not in text, "Recent Output should not be in markdown source"

        session_pos = text.find("- **Session:** my-session")
        window_pos = text.find("- **Window:** my-window (#3)")
        title_pos = text.find("- **Title:** agent-a")

        assert session_pos != -1, "Session info missing"
        assert window_pos != -1, "Window info missing"
        assert title_pos != -1, "Title info missing"

        assert pane_section_start < session_pos, "Session should be inside Pane section"
        assert pane_section_start < window_pos, "Window should be inside Pane section"
        assert pane_section_start < title_pos, "Title should be inside Pane section"

        assert session_pos < window_pos < title_pos, "Order should be Session -> Window -> Title"

        # Ensure output is in RichLog, not markdown
        log = panel.query_one("#detail-output", RichLog)
        lines = log.lines
        assert any("line1" in str(line) for line in lines)


@pytest.mark.asyncio
async def test_detail_panel_window_clears_richlog():
    """show_window should clear the RichLog output area."""
    panel = DetailPanel()
    session = make_session(session_name="dev", windows=[
        make_window(window_name="editor", panes=[
            make_pane(pane_id="%0", recent_lines=["line1"])
        ])
    ])
    window = session.windows[0]
    pane = window.panes[0]
    app = _run_detail_panel(panel)
    async with app.run_test():
        panel.show_pane(pane, window, session)
        log = panel.query_one("#detail-output", RichLog)
        assert len(log.lines) > 0

        panel.show_window(window, session)
        assert len(log.lines) == 0


@pytest.mark.asyncio
async def test_detail_panel_window_shows_session_first():
    """Window details should show Session before Name."""
    panel = DetailPanel()
    session = make_session(session_name="my-session", windows=[
        make_window(window_name="my-window", window_index=3, panes=[
            make_pane(pane_id="%0")
        ])
    ])
    window = session.windows[0]
    app = _run_detail_panel(panel)
    async with app.run_test():
        panel.show_window(window, session)
        text = panel._markdown_source

        window_section_start = text.find("## Window")
        session_pos = text.find("- **Session:** my-session")
        name_pos = text.find("- **Name:** my-window")

        assert window_section_start != -1
        assert session_pos != -1, "Session info missing"
        assert name_pos != -1, "Name info missing"

        assert window_section_start < session_pos < name_pos, "Session should appear before Name in Window section"


@pytest.mark.asyncio
async def test_detail_panel_window_does_not_show_pane_count():
    """Window details should not include pane count."""
    panel = DetailPanel()
    session = make_session(session_name="my-session", windows=[
        make_window(window_name="my-window", window_index=3, panes=[
            make_pane(pane_id="%0"),
            make_pane(pane_id="%1"),
        ])
    ])
    window = session.windows[0]
    app = _run_detail_panel(panel)
    async with app.run_test():
        panel.show_window(window, session)
        text = panel._markdown_source
        assert "**Panes:**" not in text


@pytest.mark.asyncio
async def test_detail_panel_session_does_not_show_counts():
    """Session details should not include window or pane counts."""
    panel = DetailPanel()
    session = make_session(session_name="my-session", windows=[
        make_window(window_name="w1", window_index=0, panes=[make_pane(pane_id="%0")]),
        make_window(window_name="w2", window_index=1, panes=[make_pane(pane_id="%1"), make_pane(pane_id="%2")]),
    ])
    app = _run_detail_panel(panel)
    async with app.run_test():
        panel.show_session(session)
        text = panel._markdown_source
        assert "**Windows:**" not in text
    assert "**Panes:**" not in text


@pytest.mark.asyncio
async def test_detail_panel_updates_on_refresh_without_cursor_change():
    """After _do_refresh, DetailPanel should update even when the selected node hasn't changed."""

    tree = make_tree(sessions=[
        make_session(session_name="dev", windows=[
            make_window(window_name="editor", panes=[
                make_pane(pane_id="%0", is_active=False)
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

        detail = app.query_one("#detail-panel", DetailPanel)
        log = detail.query_one("#detail-output", RichLog)
        initial_lines = [str(line) for line in log.lines]
        # Default mock capture content is shown after mount
        assert any("user@host:~$" in line for line in initial_lines)

        # Change the captured pane content and refresh without moving cursor
        app._client.capture_pane_content.return_value = ["new output line"]
        await app._do_refresh()
        # Wait for call_after_refresh to fire after tree repopulates
        await pilot.pause()
        await pilot.pause()

        updated_lines = [str(line) for line in log.lines]
        assert any("new output line" in line for line in updated_lines)
        assert not any("user@host:~$" in line for line in updated_lines)


@pytest.mark.asyncio
async def test_detail_panel_updates_on_poll_without_events():
    """Periodic poll without status events must still refresh DetailPanel."""
    from unittest.mock import patch

    tree = make_tree(sessions=[
        make_session(session_name="dev", windows=[
            make_window(window_name="editor", panes=[
                make_pane(pane_id="%0", is_active=False, status=PaneStatus.ACTIVE)
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

        detail = app.query_one("#detail-panel", DetailPanel)
        log = detail.query_one("#detail-output", RichLog)
        initial_lines = [str(line) for line in log.lines]
        assert any("user@host:~$" in line for line in initial_lines)

        # Build a new tree with updated recent_lines but no events
        updated_tree = make_tree(sessions=[
            make_session(session_name="dev", windows=[
                make_window(window_name="editor", panes=[
                    make_pane(
                        pane_id="%0",
                        is_active=False,
                        status=PaneStatus.ACTIVE,
                        recent_lines=["polled output"],
                    )
                ])
            ])
        ])
        # Patch watcher.poll to return updated tree with no events
        with patch.object(app._watcher, "poll", return_value=(updated_tree, [])):
            await app._poll_tmux()
            await pilot.pause()
            await pilot.pause()

        updated_lines = [str(line) for line in log.lines]
        assert any("polled output" in line for line in updated_lines)
        assert not any("user@host:~$" in line for line in updated_lines)


# ============================================================================
# Polling: error handling and backoff
# ============================================================================


