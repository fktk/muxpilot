
from muxpilot.models import PaneStatus
from muxpilot.widgets.tree_view import TmuxTreeView, _ACTIVE_ANIMATION_FRAMES
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


def test_error_pane_icon_is_emoji():
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0", status=PaneStatus.ERROR),
        ])])
    ])
    tw = TmuxTreeView()
    tw.populate(tree)
    pane_node = tw.root.children[0].children[0].children[0]
    label = pane_node.label
    # The label should contain the error emoji
    assert "🚨" in label.plain, f"ERROR pane icon should be 🚨, got: {label.plain}"


def test_active_animation_frames_defined():
    """_ACTIVE_ANIMATION_FRAMES should be a non-empty list of emoji frames."""
    assert len(_ACTIVE_ANIMATION_FRAMES) > 0
    assert isinstance(_ACTIVE_ANIMATION_FRAMES, list)
    for frame in _ACTIVE_ANIMATION_FRAMES:
        assert isinstance(frame, str)
        assert len(frame) > 0


def test_active_pane_uses_emoji_on_populate():
    """ACTIVE panes should use emoji frames even on initial populate, not 'A'."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0", status=PaneStatus.ACTIVE, is_active=True),
        ])])
    ])
    tw = TmuxTreeView()
    tw.populate(tree)
    pane_node = tw.root.children[0].children[0].children[0]
    label = pane_node.label
    # Should use the current animation frame emoji, not the letter 'A'
    assert _ACTIVE_ANIMATION_FRAMES[tw._animation_frame % len(_ACTIVE_ANIMATION_FRAMES)] in label.plain
    assert "A" not in label.plain


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
    # On populate, ACTIVE panes already use the current animation frame
    assert _ACTIVE_ANIMATION_FRAMES[0] in initial_label.plain

    tw._animate_active_icons()

    assert tw._animation_frame == 1
    new_label = pane_node.label
    assert initial_label != new_label
    # After animation, the label should contain the next animation frame
    assert _ACTIVE_ANIMATION_FRAMES[1] in new_label.plain


def test_active_animation_frames_cycle():
    """Animation frames should cycle back to the first after the last frame."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0", status=PaneStatus.ACTIVE, is_active=True),
        ])])
    ])
    tw = TmuxTreeView()
    tw.populate(tree)

    frame_count = len(_ACTIVE_ANIMATION_FRAMES)
    labels = []
    for i in range(frame_count + 1):
        tw._animation_frame = i - 1
        tw._animate_active_icons()
        pane_node = tw.root.children[0].children[0].children[0]
        labels.append(pane_node.label.plain)

    # Each frame should produce the correct label
    for i in range(frame_count):
        assert _ACTIVE_ANIMATION_FRAMES[i % frame_count] in labels[i]

    # After cycling through all frames, the next should match frame 0 again
    assert _ACTIVE_ANIMATION_FRAMES[0] in labels[frame_count]


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


def test_default_css_hides_cursor_when_blurred():
    """TmuxTreeView should override tree--cursor styles to hide highlight when not focused."""
    css = TmuxTreeView.DEFAULT_CSS
    assert "TmuxTreeView" in css
    assert "& > .tree--cursor" in css
    assert "text-style: none" in css
    assert "background: transparent" in css
    assert "&:focus" in css
    assert "$block-cursor-background" in css

