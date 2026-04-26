"""Data models for tmux session/window/pane hierarchy and pane activity tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PaneStatus(Enum):
    """Estimated status of a pane based on its output patterns."""

    ACTIVE = "active"          # 出力中（ログが流れている等）
    IDLE = "idle"              # 出力停止中
    WAITING_INPUT = "waiting"  # プロンプト表示中（指示待ち）
    ERROR = "error"            # エラーパターン検出
    COMPLETED = "completed"    # コマンド完了（シェルプロンプト復帰）
    UNKNOWN = "unknown"        # 初回・判定不能


# ステータスに対応するアイコン
STATUS_ICONS: dict[PaneStatus, str] = {
    PaneStatus.ACTIVE: "●",
    PaneStatus.IDLE: "◌",
    PaneStatus.WAITING_INPUT: "⏳",
    PaneStatus.ERROR: "🔴",
    PaneStatus.COMPLETED: "✅",
    PaneStatus.UNKNOWN: "?",
}


@dataclass
class PaneInfo:
    """Information about a single tmux pane."""

    pane_id: str
    pane_index: int
    current_command: str
    current_path: str
    is_active: bool
    width: int
    height: int
    status: PaneStatus = PaneStatus.UNKNOWN

    @property
    def display_label(self) -> str:
        """Label for tree view display."""
        icon = STATUS_ICONS.get(self.status, "?")
        path = _shorten_path(self.current_path)
        return f"{icon} {self.pane_id} [{self.current_command}] {path}"


@dataclass
class WindowInfo:
    """Information about a single tmux window."""

    window_id: str
    window_name: str
    window_index: int
    is_active: bool
    panes: list[PaneInfo] = field(default_factory=list)

    @property
    def display_label(self) -> str:
        """Label for tree view display."""
        active = " *" if self.is_active else ""
        return f"🪟 {self.window_index}: {self.window_name}{active}"


@dataclass
class SessionInfo:
    """Information about a single tmux session."""

    session_name: str
    session_id: str
    is_attached: bool
    windows: list[WindowInfo] = field(default_factory=list)

    @property
    def display_label(self) -> str:
        """Label for tree view display."""
        attached = " (attached)" if self.is_attached else ""
        return f"📦 {self.session_name}{attached}"


@dataclass
class TmuxTree:
    """Complete tmux hierarchy snapshot."""

    sessions: list[SessionInfo] = field(default_factory=list)
    timestamp: float = 0.0

    @property
    def total_sessions(self) -> int:
        return len(self.sessions)

    @property
    def total_windows(self) -> int:
        return sum(len(s.windows) for s in self.sessions)

    @property
    def total_panes(self) -> int:
        return sum(len(w.panes) for s in self.sessions for w in s.windows)

    def all_panes(self) -> list[PaneInfo]:
        """Flatten all panes from the tree."""
        return [p for s in self.sessions for w in s.windows for p in w.panes]


@dataclass
class PaneActivity:
    """Tracks pane output changes for status detection."""

    pane_id: str
    last_content_hash: str = ""
    last_line: str = ""
    idle_seconds: float = 0.0
    status: PaneStatus = PaneStatus.UNKNOWN


@dataclass
class TmuxEvent:
    """An event detected by the watcher."""

    event_type: str  # "pane_added", "pane_removed", "status_changed", etc.
    pane_id: str = ""
    session_name: str = ""
    window_name: str = ""
    old_status: PaneStatus | None = None
    new_status: PaneStatus | None = None
    message: str = ""


def _shorten_path(path: str) -> str:
    """Shorten home directory paths for display."""
    import os

    home = os.path.expanduser("~")
    if path.startswith(home):
        return "~" + path[len(home):]
    return path
