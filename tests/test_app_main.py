"""Tests for main() bootstrap when outside tmux."""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from muxpilot.app import main


@patch("muxpilot.app.os.execlp")
@patch("muxpilot.app.subprocess.run")
@patch("muxpilot.app.TmuxClient")
def test_main_outside_tmux_creates_session_and_attaches(mock_client_cls, mock_run, mock_execlp):
    """When started outside tmux, main() should create a new session and attach."""
    mock_client = MagicMock()
    mock_client.is_inside_tmux.return_value = False
    mock_client_cls.return_value = mock_client

    # os.execlp should replace the process — mock it to raise so we can verify
    mock_execlp.side_effect = SystemExit(0)

    with pytest.raises(SystemExit):
        main()

    mock_run.assert_called_once_with(
        ["tmux", "new-session", "-s", "muxpilot", "-d", sys.executable, "-m", "muxpilot"],
        check=True,
    )
    mock_execlp.assert_called_once_with(
        "tmux", "tmux", "attach", "-t", "muxpilot"
    )


@patch("muxpilot.app.os.execlp")
@patch("muxpilot.app.subprocess.run")
@patch("muxpilot.app.TmuxClient")
@patch("muxpilot.app.MuxpilotApp")
def test_main_inside_tmux_runs_app(mock_app_cls, mock_client_cls, mock_run, mock_execlp):
    """When started inside tmux, main() should run MuxpilotApp normally."""
    mock_client = MagicMock()
    mock_client.is_inside_tmux.return_value = True
    mock_client_cls.return_value = mock_client

    mock_app = MagicMock()
    mock_app.run.return_value = None
    mock_app_cls.return_value = mock_app

    main()

    mock_run.assert_not_called()
    mock_execlp.assert_not_called()
    mock_app.run.assert_called_once()


@patch("muxpilot.app.os.execlp")
@patch("muxpilot.app.subprocess.run")
@patch("muxpilot.app.TmuxClient")
def test_main_outside_tmux_attaches_even_if_session_exists(mock_client_cls, mock_run, mock_execlp):
    """If new-session fails (session already exists), main() should still try to attach."""
    mock_client = MagicMock()
    mock_client.is_inside_tmux.return_value = False
    mock_client_cls.return_value = mock_client

    mock_run.side_effect = subprocess.CalledProcessError(1, "tmux")
    mock_execlp.side_effect = SystemExit(0)

    with pytest.raises(SystemExit):
        main()

    mock_run.assert_called_once()
    mock_execlp.assert_called_once_with(
        "tmux", "tmux", "attach", "-t", "muxpilot"
    )


# ============================================================================
# Polling cooldown
# ============================================================================


