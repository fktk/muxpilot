"""Tests for filter input behavior."""

from __future__ import annotations

import pytest

from muxpilot.models import PaneStatus

from _test_app_common import _patched_app


@pytest.mark.asyncio
async def test_filter_input_toggle():
    """Pressing / should toggle filter-input visibility."""
    from textual.widgets import Input
    app = _patched_app()
    async with app.run_test() as pilot:
        fi = app.query_one("#filter-input", Input)

        # Initially hidden
        assert not fi.has_class("-active")

        # action_filter() directly — avoids key routing ambiguity
        app.action_filter()
        await pilot.pause()
        assert fi.has_class("-active")

        # Second call hides it again
        app.action_filter()
        await pilot.pause()
        assert not fi.has_class("-active")


@pytest.mark.asyncio
async def test_escape_closes_filter_input():
    """Pressing Escape should close the active filter input."""
    from textual.widgets import Input
    app = _patched_app()
    async with app.run_test() as pilot:
        await pilot.press("slash")
        assert app.query_one("#filter-input", Input).has_class("-active")
        await pilot.press("escape")
        assert not app.query_one("#filter-input", Input).has_class("-active")


# ============================================================================
# Filter: clear all (c) — call action directly
# ============================================================================


@pytest.mark.asyncio
async def test_filter_all_clears():
    """action_filter_all should clear both status and name filters."""
    from textual.widgets import Input
    app = _patched_app()
    async with app.run_test() as pilot:
        # Set some filter state directly
        app._filter_state = app._filter_state.with_status({PaneStatus.ERROR})
        await pilot.pause()
        assert app._filter_state.status_filter is not None

        # Now clear everything
        await app.action_filter_all()
        await pilot.pause()
        assert app._filter_state.status_filter is None
        assert app._filter_state.name_filter == ""
        fi = app.query_one("#filter-input", Input)
        assert not fi.has_class("-active")


# ============================================================================
# Cursor preservation: populate() must not reset cursor position
# ============================================================================


