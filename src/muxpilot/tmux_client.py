"""Wrapper around libtmux for tmux server interaction."""

from __future__ import annotations

import os
import subprocess
import time

import libtmux
import psutil

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
        self._pane_cache: dict[str, libtmux.Pane] = {}

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

        fmt = (
            "#{session_name}\t#{session_id}\t#{session_attached}\t"
            "#{window_id}\t#{window_name}\t#{window_index}\t#{window_active}\t"
            "#{pane_id}\t#{pane_index}\t#{pane_current_command}\t#{pane_current_path}\t"
            "#{pane_active}\t#{pane_width}\t#{pane_height}\t#{pane_pid}"
        )

        try:
            result = subprocess.run(
                ["tmux", "list-panes", "-a", "-F", fmt],
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            result.check_returncode()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return tree

        sessions: dict[str, SessionInfo] = {}
        windows: dict[str, WindowInfo] = {}

        for line in result.stdout.splitlines():
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 15:
                continue

            session_name = parts[0]
            session_id = parts[1]
            session_attached = _is_attached_str(parts[2])

            window_id = parts[3]
            window_name = parts[4]
            window_index = int(parts[5] or 0)
            window_active = _is_active_str(parts[6])

            pane_id = parts[7]
            pane_index = int(parts[8] or 0)
            current_command = parts[9]
            current_path = parts[10]
            pane_active = _is_active_str(parts[11])
            width = int(parts[12] or 0)
            height = int(parts[13] or 0)

            if session_id not in sessions:
                sessions[session_id] = SessionInfo(
                    session_name=session_name,
                    session_id=session_id,
                    is_attached=session_attached,
                    windows=[],
                )

            if window_id not in windows:
                window_info = WindowInfo(
                    window_id=window_id,
                    window_name=window_name,
                    window_index=window_index,
                    is_active=window_active,
                    panes=[],
                )
                windows[window_id] = window_info
                sessions[session_id].windows.append(window_info)

            pane_info = PaneInfo(
                pane_id=pane_id,
                pane_index=pane_index,
                current_command=current_command,
                current_path=current_path,
                is_active=pane_active,
                width=width,
                height=height,
                is_self=(pane_id == self_pane_id),
                full_command="",
            )
            windows[window_id].panes.append(pane_info)

        tree.sessions = list(sessions.values())
        return tree

    def navigate_to(self, pane_id: str) -> bool:
        """
        Navigate to the specified pane.

        Uses tmux switch-client with pane_id directly, which handles
        cross-session, cross-window navigation automatically without
        relying on cached libtmux objects that may become stale.
        """
        try:
            self.server.cmd("switch-client", "-t", pane_id)
            return True
        except libtmux.exc.LibTmuxException:
            return False

    def kill_pane(self, pane_id: str) -> bool:
        """Kill the specified pane."""
        pane = self._find_pane(pane_id)
        if pane is None:
            return False
        try:
            pane.kill()
            return True
        except libtmux.exc.LibTmuxException:
            return False

    def _get_full_command(self, pane: libtmux.Pane) -> str:
        """Get full command line (with arguments) for a pane using psutil.

        If the pane process is a shell with children, returns the child
        process cmdline. Falls back to pane_current_command on error.
        """
        try:
            pid = int(pane.pane_pid or 0)
            if pid == 0:
                return pane.pane_current_command or ""
            proc = psutil.Process(pid)
            children = proc.children()
            if children:
                return " ".join(children[0].cmdline())
            return " ".join(proc.cmdline())
        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError, TypeError):
            return pane.pane_current_command or ""

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
        """Find a pane object by its ID across all sessions.

        Uses a cache populated by previous calls to avoid redundant tmux commands.
        Falls back to a full server scan if the cache miss.
        """
        if pane_id in self._pane_cache:
            return self._pane_cache[pane_id]

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


def _is_attached_str(value: str) -> bool:
    """Check if a session is attached from a string value."""
    try:
        return int(value) > 0
    except (ValueError, TypeError):
        return False


def _is_active_str(value: str) -> bool:
    """Check if a window or pane is active from a string value."""
    try:
        return int(value) > 0
    except (ValueError, TypeError):
        return False
