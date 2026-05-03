"""Tree widget displaying the tmux session/window/pane hierarchy."""

from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text
from textual.message import Message
from textual.widgets import Tree
from textual.widgets._tree import TreeNode

from muxpilot.models import PaneInfo, PaneStatus, SessionInfo, TmuxTree, WindowInfo

# Pastel colors for the ACTIVE icon animation (no red)
_ANIMATION_COLORS = [
    "#FFD4A3", "#FFFFB3", "#B3FFB3", "#B3D9FF", "#D9B3FF",
]


class TmuxTreeView(Tree[Text]):
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
        super().__init__(Text("tmux"), name=name, id=id)
        self._pane_map: dict[str, tuple[SessionInfo, WindowInfo, PaneInfo]] = {}
        self._node_data: dict[int, tuple[str, SessionInfo | None, WindowInfo | None, PaneInfo | None]] = {}
        self._node_map: dict[int, TreeNode[Text]] = {}
        self._expanded_paths: set[str] = set()
        self._known_paths: set[str] = set()
        self._selected_path: str | None = None
        self._has_populated: bool = False
        self._animation_frame: int = 0

    def on_mount(self) -> None:
        """Start the ACTIVE icon animation interval."""
        self.set_interval(0.3, self._animate_active_icons)

    def get_cursor_node_data(self) -> tuple[str, SessionInfo | None, WindowInfo | None, PaneInfo | None] | None:
        """Return the data tuple for the currently cursor-selected node, or None."""
        node = self.cursor_node
        if node is None or node == self.root:
            return None
        return self._node_data.get(node.id)

    def _get_node_path(self, node: TreeNode[Text]) -> str:
        """Generate a unique string path for a node to preserve state."""
        data = self._node_data.get(node.id)
        if not data:
            return ""
        node_type, session, window, pane = data
        if node_type == "session" and session:
            return f"s:{session.session_id}"
        elif node_type == "window" and session and window:
            return f"s:{session.session_id}/w:{window.window_id}"
        elif node_type == "pane" and session and window and pane:
            return f"s:{session.session_id}/w:{window.window_id}/p:{pane.pane_id}"
        return ""

    def _save_state(self) -> None:
        """Save the expanded state of all nodes and the currently selected node."""
        self._expanded_paths.clear()
        self._known_paths.clear()
        
        # Save expanded nodes and all known nodes
        nodes_to_check: list[TreeNode[Text]] = [self.root]
        while nodes_to_check:
            node = nodes_to_check.pop(0)
            if node != self.root:
                path = self._get_node_path(node)
                if path:
                    self._known_paths.add(path)
                    if node.is_expanded:
                        self._expanded_paths.add(path)
            nodes_to_check.extend(node.children)

        # Save selected node
        if self.cursor_node and self.cursor_node != self.root:
            self._selected_path = self._get_node_path(self.cursor_node)
        else:
            self._selected_path = None

    def _restore_state(self) -> None:
        """Restore the expanded state and selection."""
        nodes_to_check: list[TreeNode[Text]] = [self.root]
        target_cursor_node = None
        
        while nodes_to_check:
            node = nodes_to_check.pop(0)
            if node != self.root:
                path = self._get_node_path(node)
                if path in self._expanded_paths or path not in self._known_paths:
                    node.expand()
                else:
                    node.collapse()
                if path == self._selected_path:
                    target_cursor_node = node
            nodes_to_check.extend(node.children)

        if target_cursor_node:
            # Defer until after rendering: newly added nodes have _line == -1
            # until the tree renders, so move_cursor() would snap to line -1
            # (top) if called synchronously here.
            self.call_after_refresh(self._move_cursor_and_emit, target_cursor_node)

    def _move_cursor_and_emit(self, node: TreeNode[Text]) -> None:
        """Move cursor to node and emit NodeInfo for the detail panel."""
        self.move_cursor(node)
        data = self._node_data.get(node.id)
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

    def populate(
        self,
        tree: TmuxTree,
        current_pane_id: str | None = None,
        status_filter: set[PaneStatus] | None = None,
        name_filter: str = ""
    ) -> None:
        """Populate (or repopulate) the tree from a TmuxTree snapshot."""
        # Only save state if the tree is not empty
        if self.root.children:
            self._save_state()
            
        self.clear()
        self._pane_map.clear()
        self._node_data.clear()
        self._node_map.clear()
        self.root.expand()
        
        name_filter_lower = name_filter.lower()

        for session in tree.sessions:
            # Check session name filter
            session_match = not name_filter_lower or name_filter_lower in session.session_name.lower()
            
            # Filter windows/panes
            windows_to_add = []
            for window in session.windows:
                window_match = not name_filter_lower or name_filter_lower in window.window_name.lower()
                
                panes_to_add = []
                for pane in window.panes:
                    if pane.is_self:
                        continue

                    # Apply status filter
                    if status_filter and pane.status not in status_filter:
                        continue
                        
                    # Apply name filter (if neither session nor window matched, check pane cmd/path)
                    if name_filter_lower and not (session_match or window_match):
                        if (name_filter_lower not in pane.current_command.lower() and 
                            name_filter_lower not in pane.current_path.lower()):
                            continue
                            
                    panes_to_add.append(pane)
                
                # If we have panes to add, or the window itself matches the filter, keep it
                if panes_to_add or (window_match and not status_filter):
                    windows_to_add.append((window, panes_to_add))
            
            # If we have windows to add, or the session itself matches the filter, keep it
            if windows_to_add or (session_match and not status_filter):
                session_node = self.root.add(
                    Text.from_markup(session.display_label),
                    expand=True,
                )
                self._node_data[session_node.id] = ("session", session, None, None)
                self._node_map[session_node.id] = session_node

                for window, panes in windows_to_add:
                    window_node = session_node.add(
                        Text.from_markup(window.display_label),
                        expand=True,
                    )
                    self._node_data[window_node.id] = ("window", session, window, None)
                    self._node_map[window_node.id] = window_node

                    for pane in panes:
                        label_text = self._build_pane_label(pane)

                        pane_node = window_node.add_leaf(label_text)
                        self._node_data[pane_node.id] = ("pane", session, window, pane)
                        self._node_map[pane_node.id] = pane_node
                        self._pane_map[pane.pane_id] = (session, window, pane)

        # Restore state after populating
        if not self._has_populated:
            self.root.expand_all()
        else:
            self._restore_state()

        self._has_populated = True

    def _animate_active_icons(self) -> None:
        """Cycle the color of ACTIVE pane icons."""
        self._animation_frame += 1
        color = _ANIMATION_COLORS[self._animation_frame % len(_ANIMATION_COLORS)]
        animated_icon = f"[{color}]A[/{color}]"

        for node_id, data in self._node_data.items():
            node_type, session, window, pane = data
            if node_type != "pane" or pane is None or pane.status != PaneStatus.ACTIVE:
                continue
            node = self._node_map.get(node_id)
            if node is not None:
                label = self._build_pane_label(pane, animated_icon)
                node.set_label(label)

    def _build_pane_label(self, pane: PaneInfo, icon: str | None = None) -> Text:
        """Build a Rich Text label for a pane, optionally overriding the icon."""
        markup = pane.get_display_label(icon_override=icon)
        label_text = Text.from_markup(markup)
        if pane.is_active:
            label_text.stylize("bold")
        else:
            label_text.stylize("dim")
        return label_text

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted[Text]) -> None:
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

    def on_tree_node_selected(self, event: Tree.NodeSelected[Text]) -> None:
        """When a node is selected (Enter), emit PaneActivated for pane/window/session."""
        data = self._node_data.get(event.node.id)
        if not data:
            return
        node_type, session, window, pane = data
        if node_type == "pane" and pane is not None:
            self.post_message(self.PaneActivated(pane_id=pane.pane_id))
        elif node_type == "window" and window is not None:
            active = next((p for p in window.panes if p.is_active), None)
            if active:
                self.post_message(self.PaneActivated(pane_id=active.pane_id))
        elif node_type == "session" and session is not None:
            active_window = next((w for w in session.windows if w.is_active), None)
            if active_window:
                active_pane = next((p for p in active_window.panes if p.is_active), None)
                if active_pane:
                    self.post_message(self.PaneActivated(pane_id=active_pane.pane_id))

