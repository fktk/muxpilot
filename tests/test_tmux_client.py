"""Tests for muxpilot.tmux_client — TmuxClient with mocked libtmux."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from muxpilot.tmux_client import (
    TmuxClient,
    _is_active_pane,
    _is_active_window,
    _is_attached,
)


def _mock_pane(pane_id="%0", cmd="bash", path="/home/user", active="1", w="80", h="24"):
    p = MagicMock()
    p.pane_id = pane_id
    p.pane_index = "0"
    p.pane_current_command = cmd
    p.pane_current_path = path
    p.pane_active = active
    p.pane_width = w
    p.pane_height = h
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


class TestGetTree:
    def test_basic(self):
        c = _client_with([_mock_session(sname="dev")])
        t = c.get_tree()
        assert t.total_sessions == 1
        assert t.sessions[0].session_name == "dev"

    def test_multiple(self):
        p = [_mock_pane(pane_id=f"%{i}") for i in range(4)]
        w1 = _mock_window(wid="@0", panes=p[:2])
        w2 = _mock_window(wid="@1", panes=[p[2]])
        w3 = _mock_window(wid="@2", panes=[p[3]])
        s1 = _mock_session(sid="$0", windows=[w1, w2])
        s2 = _mock_session(sid="$1", windows=[w3])
        t = _client_with([s1, s2]).get_tree()
        assert t.total_sessions == 2
        assert t.total_windows == 3
        assert t.total_panes == 4

    def test_empty(self):
        t = _client_with([]).get_tree()
        assert t.total_sessions == 0

    def test_none_values(self):
        p = _mock_pane()
        p.pane_current_command = None
        p.pane_current_path = None
        p.pane_width = None
        p.pane_height = None
        w = _mock_window(panes=[p])
        w.window_name = None
        w.window_index = None
        s = _mock_session(windows=[w])
        s.session_name = None
        s.session_id = None
        t = _client_with([s]).get_tree()
        pi = t.sessions[0].windows[0].panes[0]
        assert pi.current_command == ""
        assert pi.width == 0


class TestNavigateTo:
    def test_existing(self):
        p = _mock_pane(pane_id="%0")
        w = _mock_window(panes=[p])
        s = _mock_session(windows=[w])
        c = _client_with([s])
        assert c.navigate_to("%0") is True
        p.select.assert_called_once()

    def test_nonexistent(self):
        c = _client_with([_mock_session()])
        assert c.navigate_to("%99") is False

    def test_cross_session(self):
        p2 = _mock_pane(pane_id="%1")
        w2 = _mock_window(panes=[p2])
        # session.name is used by navigate_to for switch-client target
        s2 = _mock_session(sname="s2", windows=[w2], name="s2")
        # Ensure w2.session and p2.window resolve correctly
        p2.window = w2
        w2.session = s2
        c = _client_with([_mock_session(), s2])
        c.navigate_to("%1")
        c.server.cmd.assert_called_with("switch-client", "-t", "s2")


class TestCapture:
    def test_returns_list(self):
        p = _mock_pane(pane_id="%0")
        p.capture_pane.return_value = ["a", "b"]
        c = _client_with([_mock_session(windows=[_mock_window(panes=[p])])])
        assert c.capture_pane_content("%0") == ["a", "b"]

    def test_returns_string(self):
        p = _mock_pane(pane_id="%0")
        p.capture_pane.return_value = "a\nb"
        c = _client_with([_mock_session(windows=[_mock_window(panes=[p])])])
        assert c.capture_pane_content("%0") == ["a", "b"]

    def test_nonexistent(self):
        c = _client_with([_mock_session()])
        assert c.capture_pane_content("%99") == []

    def test_exception(self):
        import libtmux.exc
        p = _mock_pane(pane_id="%0")
        p.capture_pane.side_effect = libtmux.exc.LibTmuxException("fail")
        c = _client_with([_mock_session(windows=[_mock_window(panes=[p])])])
        assert c.capture_pane_content("%0") == []


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
