"""Tree widget displaying the tmux session/window/pane hierarchy."""

from __future__ import annotations

from dataclasses import dataclass

from textual.message import Message
from textual.widgets import Tree
from textual.widgets._tree import TreeNode

from muxpilot.models import PaneInfo, PaneStatus, SessionInfo, TmuxTree, WindowInfo


class TmuxTreeView(Tree[str]):
    """A tree widget that displays the tmux session → window → pane hierarchy."""

    BINDINGS = [
        ("k", "cursor_up", "Up"),
        ("j", "cursor_down", "Down"),
    ]

    @dataclass
    class PaneSelected(Message):
        """Emitted when a pane node is highlighted in the tree."""

        pane_info: PaneInfo
        window_info: WindowInfo
        session_info: SessionInfo

    @dataclass
    class PaneActivated(Message):
        """Emitted when a pane node is activated (Enter pressed)."""

        pane_id: str

    @dataclass
    class NodeInfo(Message):
        """Emitted when any node is highlighted, carrying context for the detail panel."""

        node_type: str  # "session", "window", "pane"
        session_info: SessionInfo | None = None
        window_info: WindowInfo | None = None
        pane_info: PaneInfo | None = None

    def __init__(self, name: str | None = None, id: str | None = None) -> None:
        super().__init__("tmux", name=name, id=id)
        self._pane_map: dict[str, tuple[SessionInfo, WindowInfo, PaneInfo]] = {}
        self._node_data: dict[int, tuple[str, SessionInfo | None, WindowInfo | None, PaneInfo | None]] = {}

    def populate(self, tree: TmuxTree, current_pane_id: str | None = None) -> None:
        """Populate (or repopulate) the tree from a TmuxTree snapshot."""
        self.clear()
        self._pane_map.clear()
        self._node_data.clear()
        self.root.expand()

        for session in tree.sessions:
            session_node = self.root.add(
                session.display_label,
                expand=True,
            )
            self._node_data[session_node.id] = ("session", session, None, None)

            for window in session.windows:
                window_node = session_node.add(
                    window.display_label,
                    expand=True,
                )
                self._node_data[window_node.id] = ("window", session, window, None)

                for pane in window.panes:
                    is_self = pane.pane_id == current_pane_id
                    label = pane.display_label
                    if is_self:
                        label += " (self)"

                    pane_node = window_node.add_leaf(label)
                    self._node_data[pane_node.id] = ("pane", session, window, pane)
                    self._pane_map[pane.pane_id] = (session, window, pane)

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted[str]) -> None:
        """When a node is highlighted, emit NodeInfo for the detail panel."""
        data = self._node_data.get(event.node.id)
        if data:
            node_type, session, window, pane = data
            self.post_message(
                self.NodeInfo(
                    node_type=node_type,
                    session_info=session,
                    window_info=window,
                    pane_info=pane,
                )
            )

    def on_tree_node_selected(self, event: Tree.NodeSelected[str]) -> None:
        """When a pane leaf node is selected (Enter), emit PaneActivated."""
        data = self._node_data.get(event.node.id)
        if data:
            node_type, session, window, pane = data
            if node_type == "pane" and pane is not None:
                self.post_message(self.PaneActivated(pane_id=pane.pane_id))

    def filter_by_status(self, statuses: set[PaneStatus] | None) -> None:
        """Show only panes matching the given statuses. None = show all."""
        # For simplicity in Phase 1, we just re-render with filtering
        # Full implementation in Phase 2
        pass

    def filter_by_name(self, query: str) -> None:
        """Filter sessions/windows by name. Empty string = show all."""
        # Phase 2 implementation
        pass
