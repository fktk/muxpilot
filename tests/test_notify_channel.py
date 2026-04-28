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


class TestFifoLifecycle:
    """FIFO creation and cleanup."""

    @pytest.mark.asyncio
    async def test_start_creates_fifo(self, tmp_path):
        """start() で FIFO ファイルが作成される。"""
        import stat

        fifo = tmp_path / "notify"
        ch = NotifyChannel(fifo_path=fifo)
        await ch.start()
        try:
            assert fifo.exists()
            assert stat.S_ISFIFO(fifo.stat().st_mode)
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_stop_removes_fifo(self, tmp_path):
        """stop() で FIFO ファイルが削除される。"""
        fifo = tmp_path / "notify"
        ch = NotifyChannel(fifo_path=fifo)
        await ch.start()
        await ch.stop()
        assert not fifo.exists()

    @pytest.mark.asyncio
    async def test_start_replaces_existing_fifo(self, tmp_path):
        """既存 FIFO がある場合、削除して再作成する。"""
        import os
        import stat

        fifo = tmp_path / "notify"
        os.mkfifo(fifo)
        ch = NotifyChannel(fifo_path=fifo)
        await ch.start()
        try:
            assert fifo.exists()
            assert stat.S_ISFIFO(fifo.stat().st_mode)
        finally:
            await ch.stop()


class TestFifoRead:
    """Reading messages through FIFO from external writers."""

    @pytest.mark.asyncio
    async def test_fifo_message_reaches_queue(self, tmp_path):
        """FIFO に書き込んだメッセージが receive() で取得できる。"""
        fifo = tmp_path / "notify"
        ch = NotifyChannel(fifo_path=fifo)
        await ch.start()
        try:
            def write_fifo():
                with open(fifo, "w") as f:
                    f.write("外部からの通知\n")

            await asyncio.to_thread(write_fifo)
            await asyncio.sleep(0.5)
            assert ch.receive() == "外部からの通知"
        finally:
            await ch.stop()

    @pytest.mark.asyncio
    async def test_fifo_multiple_lines(self, tmp_path):
        """FIFO に複数行書き込むと先頭の非空行だけが1回の open で読まれる。"""
        fifo = tmp_path / "notify"
        ch = NotifyChannel(fifo_path=fifo)
        await ch.start()
        try:
            def write_fifo():
                with open(fifo, "w") as f:
                    f.write("msg1\n")

            await asyncio.to_thread(write_fifo)
            await asyncio.sleep(0.5)
            assert ch.receive() == "msg1"
        finally:
            await ch.stop()
