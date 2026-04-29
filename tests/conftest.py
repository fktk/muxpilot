"""Shared fixtures and factory functions for muxpilot tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from muxpilot.models import (
    PaneInfo,
    PaneStatus,
    SessionInfo,
    TmuxTree,
    WindowInfo,
)


def make_pane(
    pane_id: str = "%0",
    pane_index: int = 0,
    current_command: str = "bash",
    current_path: str = "/home/user/project",
    is_active: bool = True,
    width: int = 80,
    height: int = 24,
    status: PaneStatus = PaneStatus.UNKNOWN,
    is_self: bool = False,
    custom_label: str = "",
    full_command: str = "",
) -> PaneInfo:
    """Create a PaneInfo with sensible defaults."""
    return PaneInfo(
        pane_id=pane_id,
        pane_index=pane_index,
        current_command=current_command,
        current_path=current_path,
        is_active=is_active,
        width=width,
        height=height,
        status=status,
        is_self=is_self,
        custom_label=custom_label,
        full_command=full_command,
    )


def make_window(
    window_id: str = "@0",
    window_name: str = "editor",
    window_index: int = 0,
    is_active: bool = True,
    panes: list[PaneInfo] | None = None,
    custom_label: str = "",
) -> WindowInfo:
    """Create a WindowInfo with sensible defaults."""
    if panes is None:
        panes = [make_pane()]
    return WindowInfo(
        window_id=window_id,
        window_name=window_name,
        window_index=window_index,
        is_active=is_active,
        panes=panes,
        custom_label=custom_label,
    )


def make_session(
    session_name: str = "main",
    session_id: str = "$0",
    is_attached: bool = True,
    windows: list[WindowInfo] | None = None,
    custom_label: str = "",
) -> SessionInfo:
    """Create a SessionInfo with sensible defaults."""
    if windows is None:
        windows = [make_window()]
    return SessionInfo(
        session_name=session_name,
        session_id=session_id,
        is_attached=is_attached,
        windows=windows,
        custom_label=custom_label,
    )


def make_tree(
    sessions: list[SessionInfo] | None = None,
    timestamp: float = 1000.0,
) -> TmuxTree:
    """Create a TmuxTree with sensible defaults."""
    if sessions is None:
        sessions = [make_session()]
    return TmuxTree(sessions=sessions, timestamp=timestamp)


def make_mock_client(
    tree: TmuxTree | None = None,
    current_pane_id: str | None = None,
    capture_content: list[str] | None = None,
) -> MagicMock:
    """Create a mock TmuxClient.

    Args:
        tree: The TmuxTree to return from get_tree().
        current_pane_id: Value for get_current_pane_id().
        capture_content: Default content for capture_pane_content().
    """
    mock = MagicMock()
    mock.get_tree.return_value = tree or make_tree()
    mock.get_current_pane_id.return_value = current_pane_id
    mock.capture_pane_content.return_value = capture_content or ["user@host:~$ "]
    mock.navigate_to.return_value = True
    mock.kill_pane.return_value = True
    mock.is_inside_tmux.return_value = current_pane_id is not None
    return mock


def make_mock_notify_channel() -> MagicMock:
    """Create a mock NotifyChannel.

    send() は何もしない、receive() は None を返す、start()/stop() は coroutine を返す。
    """
    import asyncio

    mock = MagicMock()
    mock.send.return_value = None
    mock.receive.return_value = None

    async def noop():
        pass

    mock.start = MagicMock(side_effect=lambda: noop())
    mock.stop = MagicMock(side_effect=lambda: noop())
    return mock
