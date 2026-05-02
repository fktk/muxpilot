"""Tests for muxpilot.tmux_client — TmuxClient with mocked libtmux."""

from __future__ import annotations

import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from muxpilot.tmux_client import (
    TmuxClient,
    _is_active_pane,
    _is_active_str,
    _is_active_window,
    _is_attached,
    _is_attached_str,
)


def _mock_pane(pane_id="%0", cmd="bash", path="/home/user", active="1", w="80", h="24", pid="1234", title=""):
    p = MagicMock()
    p.pane_id = pane_id
    p.pane_index = "0"
    p.pane_current_command = cmd
    p.pane_current_path = path
    p.pane_active = active
    p.pane_width = w
    p.pane_height = h
    p.pane_pid = pid
    p.pane_title = title
    return p


def _mock_window(wid="@0", name="editor", idx="0", active="1", panes=None):
    w = MagicMock()
    w.window_id = wid
    w.window_name = name
    w.window_index = idx
    w.window_active = active
    w.panes = panes or [_mock_pane()]
    return w


def _mock_session(sname="main", sid="$0", attached="1", windows=None, name=None):
    s = MagicMock()
    s.session_name = sname
    s.session_id = sid
    s.session_attached = attached
    s.name = name or sname
    s.windows = windows or [_mock_window()]
    return s


def _client_with(sessions):
    c = TmuxClient()
    mock_server = MagicMock()
    mock_server.sessions = sessions
    c._server = mock_server
    return c


class TestEnv:
    def test_inside_tmux_true(self):
        with patch.dict(os.environ, {"TMUX": "x"}):
            assert TmuxClient().is_inside_tmux() is True

    def test_inside_tmux_false(self):
        with patch.dict(os.environ, {}, clear=True):
            assert TmuxClient().is_inside_tmux() is False

    def test_pane_id_set(self):
        with patch.dict(os.environ, {"TMUX_PANE": "%1"}):
            assert TmuxClient().get_current_pane_id() == "%1"

    def test_pane_id_not_set(self):
        env = {k: v for k, v in os.environ.items() if k != "TMUX_PANE"}
        with patch.dict(os.environ, env, clear=True):
            assert TmuxClient().get_current_pane_id() is None


def _list_panes_output(lines: list[str]):
    class _Result:
        def __init__(self, stdout: str, stderr: str = "", returncode: int = 0):
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

        def check_returncode(self):
            if self.returncode != 0:
                raise subprocess.CalledProcessError(
                    self.returncode, "tmux", output=self.stdout, stderr=self.stderr
                )
    return _Result("\n".join(lines))


class TestGetTree:
    def test_basic(self):
        line = "dev\t$0\t1\t@0\teditor\t0\t1\t%0\t0\tbash\t/home/user\t1\t80\t24\t1234\tmy-pane"
        with patch("muxpilot.tmux_client.subprocess.run", return_value=_list_panes_output([line])):
            c = TmuxClient()
            t = c.get_tree()
        assert t.total_sessions == 1
        assert t.total_windows == 1
        assert t.total_panes == 1
        assert t.sessions[0].session_name == "dev"
        assert t.sessions[0].session_id == "$0"
        assert t.sessions[0].is_attached is True
        assert t.sessions[0].windows[0].window_name == "editor"
        assert t.sessions[0].windows[0].panes[0].pane_id == "%0"
        assert t.sessions[0].windows[0].panes[0].pane_title == "my-pane"

    def test_multiple(self):
        lines = [
            "s0\t$0\t1\t@0\tw0\t0\t1\t%0\t0\tbash\t/home/user\t1\t80\t24\t1234\tp0",
            "s0\t$0\t1\t@0\tw0\t0\t1\t%1\t1\tvim\t/home/user\t0\t80\t24\t1235\tp1",
            "s0\t$0\t1\t@1\tw1\t1\t0\t%2\t0\tpython\t/home/user\t1\t80\t24\t1236\tp2",
            "s1\t$1\t0\t@2\tw2\t0\t1\t%3\t0\tzsh\t/home/user\t1\t80\t24\t1237\tp3",
        ]
        with patch("muxpilot.tmux_client.subprocess.run", return_value=_list_panes_output(lines)):
            c = TmuxClient()
            t = c.get_tree()
        assert t.total_sessions == 2
        assert t.total_windows == 3
        assert t.total_panes == 4

    def test_empty(self):
        with patch("muxpilot.tmux_client.subprocess.run", return_value=_list_panes_output([])):
            c = TmuxClient()
            t = c.get_tree()
        assert t.total_sessions == 0

    def test_none_values(self):
        line = "\t" * 15
        with patch("muxpilot.tmux_client.subprocess.run", return_value=_list_panes_output([line])):
            c = TmuxClient()
            t = c.get_tree()
        pi = t.sessions[0].windows[0].panes[0]
        assert pi.current_command == ""
        assert pi.current_path == ""
        assert pi.width == 0
        assert pi.height == 0
        assert pi.pane_index == 0
        assert pi.is_active is False


class TestNavigateTo:
    def test_existing(self):
        c = _client_with([])
        assert c.navigate_to("%0") is True
        c.server.cmd.assert_called_with("switch-client", "-t", "%0")

    def test_nonexistent(self):
        import libtmux.exc
        c = _client_with([])
        c.server.cmd.side_effect = libtmux.exc.LibTmuxException("not found")
        assert c.navigate_to("%99") is False


class TestCapture:
    def test_returns_list(self):
        with patch("muxpilot.tmux_client.subprocess.run", return_value=_list_panes_output(["a", "b"])):
            c = TmuxClient()
            assert c.capture_pane_content("%0") == ["a", "b"]

    def test_returns_string(self):
        """tmux capture-pane -p returns stdout as a single string."""
        with patch("muxpilot.tmux_client.subprocess.run", return_value=_list_panes_output(["a", "b"])):
            c = TmuxClient()
            assert c.capture_pane_content("%0") == ["a", "b"]

    def test_nonexistent(self):
        with patch("muxpilot.tmux_client.subprocess.run", side_effect=subprocess.CalledProcessError(1, "tmux")):
            c = TmuxClient()
            assert c.capture_pane_content("%99") == []

    def test_exception(self):
        with patch("muxpilot.tmux_client.subprocess.run", side_effect=subprocess.TimeoutExpired("tmux", 5.0)):
            c = TmuxClient()
            assert c.capture_pane_content("%0") == []

    def test_uses_correct_lines_argument(self):
        with patch("muxpilot.tmux_client.subprocess.run", return_value=_list_panes_output(["x"])) as mock_run:
            c = TmuxClient()
            c.capture_pane_content("%0", lines=10)
        mock_run.assert_called_once_with(
            ["tmux", "capture-pane", "-p", "-t", "%0", "-S", "-10"],
            capture_output=True,
            text=True,
            timeout=5.0,
        )


class TestHelpers:
    def test_attached_true(self):
        s = MagicMock(); s.session_attached = "1"
        assert _is_attached(s) is True

    def test_attached_false(self):
        s = MagicMock(); s.session_attached = "0"
        assert _is_attached(s) is False

    def test_attached_none(self):
        s = MagicMock(); s.session_attached = None
        assert _is_attached(s) is False

    def test_attached_invalid(self):
        s = MagicMock(); s.session_attached = "abc"
        assert _is_attached(s) is False

    def test_active_window(self):
        w = MagicMock(); w.window_active = "1"
        assert _is_active_window(w) is True

    def test_active_pane(self):
        p = MagicMock(); p.pane_active = "1"
        assert _is_active_pane(p) is True


class TestGetFullCommand:
    def test_child_process(self):
        """When shell has a child process, return child's cmdline."""
        p = _mock_pane(cmd="bash", pid="1234")
        c = _client_with([])

        mock_child = MagicMock()
        mock_child.cmdline.return_value = ["python", "script.py", "--help"]
        mock_proc = MagicMock()
        mock_proc.children.return_value = [mock_child]
        mock_proc.cmdline.return_value = ["bash"]

        with patch("muxpilot.tmux_client.psutil.Process", return_value=mock_proc):
            result = c._get_full_command(p)
        assert result == "python script.py --help"

    def test_no_child_process(self):
        """When no child process, return the shell's own cmdline."""
        p = _mock_pane(cmd="bash", pid="1234")
        c = _client_with([])

        mock_proc = MagicMock()
        mock_proc.children.return_value = []
        mock_proc.cmdline.return_value = ["bash", "-l"]

        with patch("muxpilot.tmux_client.psutil.Process", return_value=mock_proc):
            result = c._get_full_command(p)
        assert result == "bash -l"

    def test_process_not_found(self):
        """Fallback to pane_current_command when process is gone."""
        import psutil
        p = _mock_pane(cmd="bash", pid="1234")
        c = _client_with([])

        with patch("muxpilot.tmux_client.psutil.Process", side_effect=psutil.NoSuchProcess(1234)):
            result = c._get_full_command(p)
        assert result == "bash"

    def test_access_denied(self):
        """Fallback to pane_current_command on permission error."""
        import psutil
        p = _mock_pane(cmd="bash", pid="1234")
        c = _client_with([])

        with patch("muxpilot.tmux_client.psutil.Process", side_effect=psutil.AccessDenied(1234)):
            result = c._get_full_command(p)
        assert result == "bash"


class TestPaneTitleAndGit:
    def test_get_tree_reads_pane_title(self):
        line = "s\t$1\t1\t@1\tw\t0\t1\t%1\t0\tbash\t/home/user\t1\t80\t24\t1234\tagent-1"
        with patch("muxpilot.tmux_client.subprocess.run", return_value=_list_panes_output([line])):
            c = TmuxClient()
            with patch.object(c, "_get_git_info", return_value={"repo_name": "", "branch": ""}):
                tree = c.get_tree()
        pane = tree.sessions[0].windows[0].panes[0]
        assert pane.pane_title == "agent-1"

    def test_get_tree_populates_git_info(self):
        line = "s\t$1\t1\t@1\tw\t0\t1\t%1\t0\tbash\t/home/user/proj\t1\t80\t24\t1234\t"
        with patch("muxpilot.tmux_client.subprocess.run", return_value=_list_panes_output([line])):
            c = TmuxClient()
            with patch.object(c, "_get_git_info", return_value={"repo_name": "proj", "branch": "main"}):
                tree = c.get_tree()
        pane = tree.sessions[0].windows[0].panes[0]
        assert pane.repo_name == "proj"
        assert pane.branch == "main"

    def test_get_git_info_success(self):
        c = _client_with([])
        with patch("muxpilot.tmux_client.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(stdout="/home/user/proj\n", returncode=0),
                MagicMock(stdout="feature/x\n", returncode=0),
            ]
            result = c._get_git_info("/home/user/proj")
        assert result == {"repo_name": "proj", "branch": "feature/x"}

    def test_get_git_info_not_a_repo(self):
        import subprocess
        c = _client_with([])
        with patch("muxpilot.tmux_client.subprocess.run", side_effect=subprocess.CalledProcessError(128, "git")):
            result = c._get_git_info("/tmp")
        assert result == {"repo_name": "", "branch": ""}

    def test_set_pane_title_calls_tmux(self):
        c = _client_with([])
        result = c.set_pane_title("%1", "new-title")
        c.server.cmd.assert_called_once_with("select-pane", "-t", "%1", "-T", "new-title")
        assert result is True

    def test_set_pane_title_failure(self):
        import libtmux.exc
        c = _client_with([])
        c.server.cmd.side_effect = libtmux.exc.LibTmuxException("fail")
        result = c.set_pane_title("%1", "new-title")
        assert result is False
