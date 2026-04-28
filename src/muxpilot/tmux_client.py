"""Wrapper around libtmux for tmux server interaction."""

from __future__ import annotations

import os
import time

import libtmux

from muxpilot.models import (
    PaneInfo,
    SessionInfo,
    TmuxTree,
    WindowInfo,
)


class TmuxClient:
    """Client for interacting with the tmux server via libtmux."""

    def __init__(self) -> None:
        self._server: libtmux.Server | None = None

    @property
    def server(self) -> libtmux.Server:
        """Lazily connect to the tmux server."""
        if self._server is None:
            self._server = libtmux.Server()
        return self._server

    def is_inside_tmux(self) -> bool:
        """Check if we are running inside a tmux session."""
        return "TMUX" in os.environ

    def get_current_pane_id(self) -> str | None:
        """Get the pane ID of the pane where muxpilot is running."""
        return os.environ.get("TMUX_PANE")

    def get_tree(self) -> TmuxTree:
        """Fetch the complete tmux session/window/pane hierarchy."""
        tree = TmuxTree(timestamp=time.time())
        self_pane_id = self.get_current_pane_id()

        for session in self.server.sessions:
            session_info = SessionInfo(
                session_name=session.session_name or "",
                session_id=session.session_id or "",
                is_attached=_is_attached(session),
                windows=[],
            )

            for window in session.windows:
                window_info = WindowInfo(
                    window_id=window.window_id or "",
                    window_name=window.window_name or "",
                    window_index=int(window.window_index or 0),
                    is_active=_is_active_window(window),
                    panes=[],
                )

                for pane in window.panes:
                    pane_id = pane.pane_id or ""
                    pane_info = PaneInfo(
                        pane_id=pane_id,
                        pane_index=int(pane.pane_index or 0),
                        current_command=pane.pane_current_command or "",
                        current_path=pane.pane_current_path or "",
                        is_active=_is_active_pane(pane),
                        width=int(pane.pane_width or 0),
                        height=int(pane.pane_height or 0),
                        is_self=(pane_id == self_pane_id),
                    )
                    window_info.panes.append(pane_info)

                session_info.windows.append(window_info)

            tree.sessions.append(session_info)

        return tree

    def navigate_to(self, pane_id: str) -> bool:
        """
        Navigate to the specified pane.

        Handles cross-session, cross-window navigation:
        1. Find the pane, its window, and session
        2. switch-client to the session (if different)
        3. select the window
        4. select the pane
        """
        target_pane = self._find_pane(pane_id)
        if target_pane is None:
            return False

        target_window = target_pane.window
        target_session = target_window.session

        # Switch client to the target session
        try:
            self.server.cmd("switch-client", "-t", target_session.name)
        except libtmux.exc.LibTmuxException:
            pass  # Already in this session

        # Select the window, then the pane
        target_window.select()
        target_pane.select()
        return True

    def capture_pane_content(self, pane_id: str, lines: int = 50) -> list[str]:
        """Capture the last N lines of output from a pane."""
        pane = self._find_pane(pane_id)
        if pane is None:
            return []

        try:
            start_line = -lines
            content = pane.capture_pane(start=start_line, end=-1)
            if isinstance(content, str):
                return content.splitlines()
            if isinstance(content, list):
                return content
            return []
        except libtmux.exc.LibTmuxException:
            return []

    def _find_pane(self, pane_id: str) -> libtmux.Pane | None:
        """Find a pane object by its ID across all sessions."""
        for session in self.server.sessions:
            for window in session.windows:
                for pane in window.panes:
                    if pane.pane_id == pane_id:
                        return pane
        return None


def _is_attached(session: libtmux.Session) -> bool:
    """Check if a session is attached."""
    try:
        return int(session.session_attached or 0) > 0
    except (ValueError, TypeError):
        return False


def _is_active_window(window: libtmux.Window) -> bool:
    """Check if a window is the active window in its session."""
    try:
        return int(window.window_active or 0) > 0
    except (ValueError, TypeError):
        return False


def _is_active_pane(pane: libtmux.Pane) -> bool:
    """Check if a pane is the active pane in its window."""
    try:
        return int(pane.pane_active or 0) > 0
    except (ValueError, TypeError):
        return False
