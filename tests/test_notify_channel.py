"""Tests for NotifyChannel."""

from __future__ import annotations

import asyncio

import pytest

from muxpilot.notify_channel import NotifyChannel


class TestSendReceive:
    """Queue-based send/receive without FIFO."""

    def test_send_then_receive(self, tmp_path):
        """send() したメッセージが receive() で取得できる。"""
        ch = NotifyChannel(fifo_path=tmp_path / "notify")
        ch.send("hello")
        assert ch.receive() == "hello"

    def test_receive_empty_returns_none(self, tmp_path):
        """Queue が空のとき receive() は None を返す。"""
        ch = NotifyChannel(fifo_path=tmp_path / "notify")
        assert ch.receive() is None

    def test_multiple_messages_in_order(self, tmp_path):
        """複数メッセージが送信順に取得できる。"""
        ch = NotifyChannel(fifo_path=tmp_path / "notify")
        ch.send("first")
        ch.send("second")
        ch.send("third")
        assert ch.receive() == "first"
        assert ch.receive() == "second"
        assert ch.receive() == "third"
        assert ch.receive() is None
