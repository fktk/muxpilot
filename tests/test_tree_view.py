import pytest

from muxpilot.models import PaneStatus
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


def test_error_pane_icon_is_red():
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0", status=PaneStatus.ERROR),
        ])])
    ])
    tw = TmuxTreeView()
    tw.populate(tree)
    pane_node = tw.root.children[0].children[0].children[0]
    label = pane_node.label
    # The label should contain a red-styled span
    assert any("red" in (span.style or "") for span in label.spans), \
        f"ERROR pane icon should be red, got spans: {label.spans}"


def test_active_pane_label_animated():
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0", status=PaneStatus.ACTIVE, is_active=True),
        ])])
    ])
    tw = TmuxTreeView()
    tw.populate(tree)
    pane_node = tw.root.children[0].children[0].children[0]
    initial_label = pane_node.label

    tw._animation_frame = 0
    tw._animate_active_icons()

    assert tw._animation_frame == 1
    new_label = pane_node.label
    assert initial_label != new_label


def test_new_window_is_auto_expanded():
    """Newly added windows should be expanded automatically."""
    tree1 = make_tree(sessions=[
        make_session(session_id="$0", windows=[
            make_window(window_id="@0", panes=[
                make_pane(pane_id="%0"),
            ])
        ])
    ])
    tw = TmuxTreeView()
    tw.populate(tree1)

    # First population: everything expanded by default
    session_node = tw.root.children[0]
    window1_node = session_node.children[0]
    assert window1_node.is_expanded

    # Collapse the existing window manually to simulate user action
    window1_node.collapse()
    assert not window1_node.is_expanded

    # Second population: add a new window
    tree2 = make_tree(sessions=[
        make_session(session_id="$0", windows=[
            make_window(window_id="@0", panes=[
                make_pane(pane_id="%0"),
            ]),
            make_window(window_id="@1", panes=[
                make_pane(pane_id="%1"),
            ]),
        ])
    ])
    tw.populate(tree2)

    session_node = tw.root.children[0]
    window1_node = session_node.children[0]
    window2_node = session_node.children[1]

    # Previously existing window should stay collapsed
    assert not window1_node.is_expanded
    # New window should be auto-expanded
    assert window2_node.is_expanded


