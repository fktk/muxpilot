"""Tests for the FilterBar widget."""

from __future__ import annotations


from muxpilot.models import PaneStatus


def test_filter_bar_shows_error_filter():
    from muxpilot.widgets.filter_bar import FilterBar
    bar = FilterBar()
    bar.update(status_filter={PaneStatus.ERROR}, name_filter="")
    assert "error" in str(bar.render())


def test_filter_bar_shows_name_filter():
    from muxpilot.widgets.filter_bar import FilterBar
    bar = FilterBar()
    bar.update(status_filter=None, name_filter="foo")
    assert "foo" in str(bar.render())


def test_filter_bar_shows_combined_filters():
    from muxpilot.widgets.filter_bar import FilterBar
    bar = FilterBar()
    bar.update(status_filter={PaneStatus.ERROR}, name_filter="foo")
    assert "error" in str(bar.render())
    assert "foo" in str(bar.render())


def test_filter_bar_hidden_when_no_filters():
    from muxpilot.widgets.filter_bar import FilterBar
    bar = FilterBar()
    bar.update(status_filter=None, name_filter="")
    assert not bar.has_class("-active")
