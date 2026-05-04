"""Controllers extracted from MuxpilotApp to reduce its responsibilities."""

from __future__ import annotations

from dataclasses import dataclass

from muxpilot.models import PaneStatus, TmuxTree


@dataclass(frozen=True)
class FilterState:
    """Immutable filter criteria. Use replace() to create modified copies."""

    status_filter: set[PaneStatus] | None = None
    name_filter: str = ""

    def cleared(self) -> FilterState:
        """Return a new FilterState with all filters removed."""
        return FilterState(status_filter=None, name_filter="")

    def with_status(self, status: set[PaneStatus] | None) -> FilterState:
        """Return a new FilterState with the given status filter."""
        return FilterState(status_filter=status, name_filter=self.name_filter)

    def with_name(self, name: str) -> FilterState:
        """Return a new FilterState with the given name filter."""
        return FilterState(status_filter=self.status_filter, name_filter=name)


class NodeRenameManager:
    """Manages the in-progress rename operation for a tree node.

    Supports pane, window, and session renaming via TmuxClient.
    """

    def __init__(self, client=None) -> None:
        self._client = client
        self._key: str | None = None
        self._target_id: str | None = None
        self._node_type: str | None = None

    @property
    def key(self) -> str | None:
        return self._key

    @key.setter
    def key(self, value: str | None) -> None:
        self._key = value

    def start(self, node_data: tuple[str, ...] | None) -> str | None:
        """Begin a rename for the given node data.

        Returns the current name (or empty string) if a rename can
        start, or None if the node data does not support renaming.
        """
        if node_data is None:
            return None
        node_type, session, window, pane = node_data
        if node_type == "pane" and session and window and pane:
            self._key = f"{session.session_name}.{window.window_index}.{pane.pane_index}"
            self._target_id = pane.pane_id
            self._node_type = "pane"
            return pane.pane_title
        elif node_type == "window" and session and window:
            self._key = f"{session.session_name}.{window.window_index}"
            self._target_id = window.window_id
            self._node_type = "window"
            return window.window_name
        elif node_type == "session" and session:
            self._key = session.session_name
            self._target_id = session.session_id
            self._node_type = "session"
            return session.session_name
        return None

    def finish(self, value: str) -> str | None:
        """Commit the rename and return the affected key, or None."""
        key = self._key
        if key is None or self._client is None:
            return None
        if self._node_type == "pane":
            self._client.set_pane_title(self._target_id or "", value)
        elif self._node_type == "window":
            self._client.rename_window(self._target_id or "", value)
        elif self._node_type == "session":
            if not value:
                self._key = None
                self._target_id = None
                self._node_type = None
                return None
            self._client.rename_session(self._target_id or "", value)
        self._key = None
        self._target_id = None
        self._node_type = None
        return key

    def cancel(self) -> None:
        """Abort the rename without saving."""
        self._key = None
        self._target_id = None
        self._node_type = None

    def apply(self, tree: TmuxTree) -> None:
        """No-op: names come from tmux directly on next poll."""
        pass


# Backward compatibility alias for existing imports
PaneTitleManager = NodeRenameManager
