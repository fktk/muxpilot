"""Controllers extracted from MuxpilotApp to reduce its responsibilities."""

from __future__ import annotations

from dataclasses import dataclass, field

from muxpilot.models import PaneStatus, TmuxTree
from muxpilot.tmux_client import TmuxClient
from muxpilot.timer_coordinator import (
    DEFAULT_COOLDOWN_SECONDS,
    DEFAULT_MAX_CONSECUTIVE_FAILURES,
    MAX_POLL_BACKOFF_SECONDS,
    TimerCoordinator,
)


# Backward-compatible alias
PollingController = TimerCoordinator


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


class PaneTitleManager:
    """Manages the in-progress rename operation for a tree node.

    Pane renames are applied directly to tmux via TmuxClient.set_pane_title().
    Session/window renaming is not supported.
    """

    def __init__(self, client=None) -> None:
        self._client = client
        self._key: str | None = None
        self._pane_id: str | None = None

    @property
    def key(self) -> str | None:
        return self._key

    @key.setter
    def key(self, value: str | None) -> None:
        self._key = value

    def start(self, node_data: tuple[str, ...] | None) -> str | None:
        """Begin a rename for the given node data.

        Returns the current pane_title (or empty string) if a rename can
        start, or None if the node data does not support renaming.
        """
        if node_data is None:
            return None
        node_type, session, window, pane = node_data
        if node_type == "pane" and session and window and pane:
            self._key = f"{session.session_name}.{window.window_index}.{pane.pane_index}"
            self._pane_id = pane.pane_id
            return pane.pane_title
        return None

    def finish(self, value: str) -> str | None:
        """Commit the rename and return the affected key, or None."""
        key = self._key
        if key is None or self._client is None:
            return None
        self._client.set_pane_title(self._pane_id or "", value)
        self._key = None
        self._pane_id = None
        return key

    def cancel(self) -> None:
        """Abort the rename without saving."""
        self._key = None
        self._pane_id = None

    def apply(self, tree: TmuxTree) -> None:
        """No-op: pane_title comes from tmux directly on next poll."""
        pass


# Backward-compatible alias
RenameController = PaneTitleManager
