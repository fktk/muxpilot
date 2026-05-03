"""Parse tmux list-panes TSV output into TmuxTree."""

from __future__ import annotations

from muxpilot.models import PaneInfo, SessionInfo, TmuxTree, WindowInfo


class TreeParser:
    """Parse the tab-separated output of tmux list-panes -F into a TmuxTree."""

    @staticmethod
    def parse_list_panes_output(stdout: str, self_pane_id: str | None = None) -> TmuxTree:
        """Parse tmux list-panes output and return a TmuxTree.

        Args:
            stdout: The raw output from ``tmux list-panes -a -F ...``.
            self_pane_id: The pane ID of the running application. Matched panes
                will have ``is_self=True``.
        """
        tree = TmuxTree()
        sessions: dict[str, SessionInfo] = {}
        windows: dict[str, WindowInfo] = {}

        for line in stdout.splitlines():
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 16:
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
            pane_title = parts[15]

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
                pane_title=pane_title,
            )
            windows[window_id].panes.append(pane_info)

        tree.sessions = list(sessions.values())
        return tree


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
