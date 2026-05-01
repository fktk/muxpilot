"""Controllers extracted from MuxpilotApp to reduce its responsibilities."""

from __future__ import annotations

import asyncio

from muxpilot.models import PaneStatus, TmuxEvent, TmuxTree
from muxpilot.tmux_client import TmuxClient
from muxpilot.watcher import TmuxWatcher


MAX_POLL_BACKOFF_SECONDS = 30.0


class PollingController:
    """Manages periodic polling, retry backoff, and timer lifecycle."""

    def __init__(
        self,
        app,
        watcher: TmuxWatcher,
        notify_channel,
    ) -> None:
        self._app = app
        self._watcher = watcher
        self._notify = notify_channel
        self._backoff = watcher.poll_interval
        self._poll_timer = None
        self._retry_timer = None

    @property
    def backoff(self) -> float:
        return self._backoff

    @backoff.setter
    def backoff(self, value: float) -> None:
        self._backoff = value

    @property
    def poll_timer(self):
        return self._poll_timer

    @poll_timer.setter
    def poll_timer(self, value) -> None:
        self._poll_timer = value

    @property
    def retry_timer(self):
        return self._retry_timer

    @retry_timer.setter
    def retry_timer(self, value) -> None:
        self._retry_timer = value

    def start(self) -> None:
        """Start the periodic polling timer."""
        self._poll_timer = self._app.set_interval(
            self._watcher.poll_interval, self._app._poll_tmux
        )

    def stop(self) -> None:
        """Stop all timers."""
        if self._poll_timer is not None:
            self._poll_timer.stop()
        if self._retry_timer is not None:
            self._retry_timer.stop()

    async def tick(self) -> tuple[TmuxTree, list[TmuxEvent]] | None:
        """Execute one poll cycle with error handling and backoff.

        Returns (tree, events) on success, or None on failure (backoff applied).
        """
        try:
            tree, events = await asyncio.to_thread(self._watcher.poll)
        except Exception as e:
            if self._watcher.notify_poll_errors:
                self._notify.send(f"tmux poll failed: {e}; retrying in {self._backoff}s")
            self._backoff = min(self._backoff * 2, MAX_POLL_BACKOFF_SECONDS)
            if self._poll_timer is not None:
                self._poll_timer.pause()
            if self._retry_timer is not None:
                self._retry_timer.stop()
            self._retry_timer = self._app.set_interval(
                self._backoff, self._app._poll_tmux, repeat=False
            )
            return None

        self._backoff = self._watcher.poll_interval
        if self._poll_timer is not None:
            self._poll_timer.resume()
        return tree, events


class FilterState:
    """Holds and mutates the active filter criteria."""

    def __init__(self) -> None:
        self.status_filter: set[PaneStatus] | None = None
        self.name_filter: str = ""

    def clear_all(self) -> None:
        """Remove all filters."""
        self.status_filter = None
        self.name_filter = ""


class RenameController:
    """Manages the in-progress rename operation for a tree node.

    Labels are kept only in memory (overlays).  They are never persisted to
    disk — when the muxpilot process exits the overlays are lost.
    """

    def __init__(self) -> None:
        self._overlays: dict[str, str] = {}
        self._key: str | None = None

    @property
    def key(self) -> str | None:
        return self._key

    @key.setter
    def key(self, value: str | None) -> None:
        self._key = value

    def get(self, key: str) -> str:
        """Return the in-memory overlay label for *key*, or empty string."""
        return self._overlays.get(key, "")

    def set(self, key: str, value: str) -> None:
        """Set (or delete if empty) an in-memory overlay label."""
        if not value:
            self.delete(key)
            return
        self._overlays[key] = value

    def delete(self, key: str) -> None:
        """Remove an in-memory overlay label."""
        self._overlays.pop(key, None)

    def start(self, node_data: tuple[str, ...] | None) -> str | None:
        """Begin a rename for the given node data.

        Returns the current overlay label (or empty string) if a rename can
        start, or None if the node data does not support renaming.
        """
        if node_data is None:
            return None
        node_type, session, window, pane = node_data
        if node_type == "session" and session:
            self._key = session.session_name
        elif node_type == "window" and session and window:
            self._key = f"{session.session_name}.{window.window_index}"
        elif node_type == "pane" and session and window and pane:
            self._key = f"{session.session_name}.{window.window_index}.{pane.pane_index}"
        else:
            return None
        return self.get(self._key)

    def finish(self, value: str) -> str | None:
        """Commit the rename and return the affected key, or None."""
        key = self._key
        if key is None:
            return None
        self.set(key, value)
        self._key = None
        return key

    def cancel(self) -> None:
        """Abort the rename without saving."""
        self._key = None

    def apply(self, tree: TmuxTree) -> None:
        """Apply in-memory overlay labels to a tree snapshot."""
        for session in tree.sessions:
            label = self._overlays.get(session.session_name)
            if label is not None:
                session.custom_label = label
            for window in session.windows:
                key = f"{session.session_name}.{window.window_index}"
                label = self._overlays.get(key)
                if label is not None:
                    window.custom_label = label
                for pane in window.panes:
                    key = f"{session.session_name}.{window.window_index}.{pane.pane_index}"
                    label = self._overlays.get(key)
                    if label is not None:
                        pane.custom_label = label
