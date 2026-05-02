"""Data models for tmux session/window/pane hierarchy and pane activity tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PaneStatus(Enum):
    """Estimated status of a pane based on its output patterns."""

    ACTIVE = "active"          # 実行中（出力変化あり、または変化停止中）
    WAITING_INPUT = "waiting"  # プロンプト表示中（指示待ち）
    ERROR = "error"            # エラーパターン検出
    IDLE = "idle"              # 一定時間以上出力変化なし


# ステータスに対応するアイコン
STATUS_ICONS: dict[PaneStatus, str] = {
    PaneStatus.ACTIVE: "[bold]A[/bold]",
    PaneStatus.WAITING_INPUT: "[bold]W[/bold]",
    PaneStatus.ERROR: "[bold red]E[/bold red]",
    PaneStatus.IDLE: "[bold]I[/bold]",
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
    status: PaneStatus = PaneStatus.ACTIVE
    is_self: bool = False
    custom_label: str = ""
    full_command: str = ""
    pane_title: str = ""
    repo_name: str = ""
    branch: str = ""
    idle_seconds: float = 0.0
    recent_lines: list[str] = field(default_factory=list)

    def get_display_label(self, icon_override: str | None = None) -> str:
        """Label for tree view display.

        Args:
            icon_override: If given, replaces the default status icon markup.
        """
        icon = icon_override if icon_override is not None else STATUS_ICONS.get(self.status, "?")
        if self.pane_title:
            return f"{icon} {self.pane_title}"
        if self.custom_label:
            return f"{icon} {self.custom_label}"

        # Use only the last path component unless it is too generic
        path = self.current_path.rstrip("/")
        parts = path.split("/")
        if len(parts) >= 2:
            short_path = f"{parts[-2]}/{parts[-1]}"
        else:
            short_path = parts[-1] if parts else ""

        # Prefer a concise command; skip bare shells if we have a child process
        cmd = self.full_command or self.current_command
        shell_names = {"bash", "zsh", "fish", "sh", "tmux"}
        if self.current_command in shell_names and self.full_command:
            cmd = self.full_command.split()[0].split("/")[-1] if self.full_command else self.current_command
        else:
            cmd = self.current_command or self.full_command

        return f"{icon} {cmd} — {short_path}"

    @property
    def display_label(self) -> str:
        """Label for tree view display."""
        return self.get_display_label()


@dataclass
class WindowInfo:
    """Information about a single tmux window."""

    window_id: str
    window_name: str
    window_index: int
    is_active: bool
    panes: list[PaneInfo] = field(default_factory=list)
    custom_label: str = ""

    @property
    def display_label(self) -> str:
        """Label for tree view display."""
        if self.custom_label:
            return f"□ {self.custom_label}"
        active = " *" if self.is_active else ""
        return f"□ {self.window_index}: {self.window_name}{active}"


@dataclass
class SessionInfo:
    """Information about a single tmux session."""

    session_name: str
    session_id: str
    is_attached: bool
    windows: list[WindowInfo] = field(default_factory=list)
    custom_label: str = ""

    @property
    def display_label(self) -> str:
        """Label for tree view display."""
        if self.custom_label:
            return f"■ {self.custom_label}"
        attached = " (attached)" if self.is_attached else ""
        return f"■ {self.session_name}{attached}"


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
    status: PaneStatus = PaneStatus.ACTIVE
    content_changed: bool = False
    recent_lines: list[str] = field(default_factory=list)


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
