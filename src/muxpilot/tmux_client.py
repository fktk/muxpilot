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
        pane_cache: dict[str, libtmux.Pane] = {}

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
                    if pane_id:
                        pane_cache[pane_id] = pane
                    pane_info = PaneInfo(
                        pane_id=pane_id,
                        pane_index=int(pane.pane_index or 0),
                        current_command=pane.pane_current_command or "",
                        current_path=pane.pane_current_path or "",
                        is_active=_is_active_pane(pane),
                        width=int(pane.pane_width or 0),
                        height=int(pane.pane_height or 0),
                        is_self=(pane_id == self_pane_id),
                        full_command=self._get_full_command(pane),
                        pane_title=pane.pane_title or "",
                    )
                    git_info = self._get_git_info(pane_info.current_path)
                    pane_info.repo_name = git_info["repo_name"]
                    pane_info.branch = git_info["branch"]
                    window_info.panes.append(pane_info)

                session_info.windows.append(window_info)

            tree.sessions.append(session_info)

        # Update pane cache so subsequent lookups (e.g. capture_pane) don't
        # re-fetch the entire tree via N+1 tmux commands.
        self._pane_cache = pane_cache

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

    def _get_git_info(self, path: str) -> dict[str, str]:
        """Get repository name and current branch for a path."""
        result = {"repo_name": "", "branch": ""}
        if not path:
            return result
        try:
            top = subprocess.run(
                ["git", "-C", path, "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=1.0, check=True,
            ).stdout.strip()
            result["repo_name"] = top.split("/")[-1] if top else ""
            branch = subprocess.run(
                ["git", "-C", path, "branch", "--show-current"],
                capture_output=True, text=True, timeout=1.0, check=True,
            ).stdout.strip()
            result["branch"] = branch
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return result

    def set_pane_title(self, pane_id: str, title: str) -> bool:
        """Set the tmux pane title."""
        try:
            self.server.cmd("select-pane", "-t", pane_id, "-T", title)
            return True
        except Exception:
            return False

    def _find_pane(self, pane_id: str) -> libtmux.Pane | None:
        """Find a pane object by its ID across all sessions.

        Uses a cache populated by get_tree() to avoid redundant tmux commands.
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
