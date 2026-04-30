import pytest

from muxpilot.widgets.tree_view import TmuxTreeView
from conftest import make_tree, make_session, make_window, make_pane


def test_inactive_pane_is_dimmed():
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0", is_active=False),
        ])])
    ])
    tw = TmuxTreeView()
    tw.populate(tree)
    pane_node = tw.root.children[0].children[0].children[0]
    label = pane_node.label
    # rich.Text.spans contains style info
    assert any("dim" in (span.style or "") for span in label.spans)


def test_active_pane_is_not_dimmed():
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0", is_active=True),
        ])])
    ])
    tw = TmuxTreeView()
    tw.populate(tree)
    pane_node = tw.root.children[0].children[0].children[0]
    label = pane_node.label
    assert not any("dim" in (span.style or "") for span in label.spans)


def test_self_pane_hidden():
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0"),
            make_pane(pane_id="%1", is_self=True),
        ])])
    ])
    tw = TmuxTreeView()
    tw.populate(tree, current_pane_id="%1")
    assert "%1" not in tw._pane_map


