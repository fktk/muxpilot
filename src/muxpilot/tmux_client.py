"""Wrapper around libtmux for tmux server interaction."""

from __future__ import annotations

import os
import subprocess
import time

import libtmux

from muxpilot.models import TmuxTree
from muxpilot.tree_parser import TreeParser


class TmuxClient:
    """Client for interacting with the tmux server."""

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
            "#{pane_active}\t#{pane_width}\t#{pane_height}\t#{pane_pid}\t#{pane_title}"
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

        tree = TreeParser.parse_list_panes_output(result.stdout, self_pane_id)
        tree.timestamp = time.time()

        # Attach git metadata (not available from tmux format strings)
        for session in tree.sessions:
            for window in session.windows:
                for pane in window.panes:
                    git_info = self._get_git_info(pane.current_path)
                    pane.repo_name = git_info["repo_name"]
                    pane.branch = git_info["branch"]

        return tree

    def navigate_to(self, pane_id: str) -> bool:
        """
        Navigate to the specified pane.

        Uses tmux switch-client with pane_id directly, which handles
        cross-session, cross-window navigation automatically without
        relying on cached libtmux objects that may become stale.
        """
        server = libtmux.Server()
        try:
            server.cmd("switch-client", "-t", pane_id)
            return True
        except libtmux.exc.LibTmuxException:
            return False

    def kill_pane(self, pane_id: str) -> bool:
        """Kill the specified pane via subprocess."""
        try:
            subprocess.run(
                ["tmux", "kill-pane", "-t", pane_id],
                capture_output=True,
                check=True,
                timeout=5.0,
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    def capture_pane_content(self, pane_id: str, lines: int = 50) -> list[str]:
        """Capture the last N lines of output from a pane via subprocess."""
        try:
            result = subprocess.run(
                ["tmux", "capture-pane", "-p", "-t", pane_id, "-S", f"-{lines}"],
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            result.check_returncode()
            return result.stdout.splitlines()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
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
        server = libtmux.Server()
        try:
            server.cmd("select-pane", "-t", pane_id, "-T", title)
            return True
        except Exception:
            return False
