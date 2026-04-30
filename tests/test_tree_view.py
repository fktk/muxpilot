import pytest

from muxpilot.widgets.tree_view import TmuxTreeView
from conftest import make_tree, make_session, make_window, make_pane


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


def test_collapsed_state_preserved_after_repopulate():
    """After collapsing all nodes with 'a', repopulate() must keep them collapsed."""
    tree = make_tree(sessions=[
        make_session(session_id="$0", session_name="s0", windows=[
            make_window(window_id="@0", panes=[make_pane(pane_id="%0")]),
            make_window(window_id="@1", window_name="w1", panes=[make_pane(pane_id="%1")]),
        ]),
    ])
    tw = TmuxTreeView()
    tw.populate(tree)

    # Collapse all nodes via action_toggle_expand
    tw.action_toggle_expand()

    # Verify all expandable nodes are collapsed
    expandable = []
    queue = [tw.root]
    while queue:
        node = queue.pop(0)
        if node != tw.root and node.allow_expand:
            expandable.append(node)
        queue.extend(node.children)
    assert all(not n.is_expanded for n in expandable), "All nodes should be collapsed after toggle"

    # Repopulate with the same tree
    tw.populate(tree)

    # Verify all expandable nodes are still collapsed
    expandable = []
    queue = [tw.root]
    while queue:
        node = queue.pop(0)
        if node != tw.root and node.allow_expand:
            expandable.append(node)
        queue.extend(node.children)
    assert all(not n.is_expanded for n in expandable), "All nodes should stay collapsed after repopulate"
