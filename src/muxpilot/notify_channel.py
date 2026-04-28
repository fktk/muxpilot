"""FIFO-based notification channel for muxpilot."""

from __future__ import annotations

import asyncio
import logging
import os
import queue
import stat
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_FIFO_PATH = Path.home() / ".muxpilot" / "notify"


class NotifyChannel:
    """Notification channel that unifies internal and external (FIFO) messages."""

    def __init__(self, fifo_path: Path = DEFAULT_FIFO_PATH) -> None:
        self.fifo_path = fifo_path
        self._queue: queue.SimpleQueue[str] = queue.SimpleQueue()
        self._running = False
        self._read_task: asyncio.Task[None] | None = None

    def send(self, message: str) -> None:
        """Add a message to the notification queue (internal use)."""
        self._queue.put(message)

    def receive(self) -> str | None:
        """Get next message from the queue, or None if empty."""
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    async def start(self) -> None:
        """Create FIFO and start the background read loop."""
        self._ensure_fifo()
        self._running = True
        self._read_task = asyncio.create_task(self._read_loop())

    async def stop(self) -> None:
        """Stop the read loop and remove the FIFO."""
        self._running = False
        if self._read_task is not None:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
            self._read_task = None
        if self.fifo_path.exists():
            self.fifo_path.unlink()

    def _ensure_fifo(self) -> None:
        """Create the FIFO file, replacing any existing one."""
        self.fifo_path.parent.mkdir(parents=True, exist_ok=True)
        if self.fifo_path.exists():
            self.fifo_path.unlink()
        os.mkfifo(self.fifo_path)

    async def _read_loop(self) -> None:
        """Background loop: read lines from FIFO and enqueue them."""
        while self._running:
            try:
                line = await asyncio.to_thread(self._read_one_line)
                if line is not None:
                    self._queue.put(line)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error reading from FIFO")
                if self._running:
                    await asyncio.sleep(0.5)

    def _read_one_line(self) -> str | None:
        """Blocking read of one line from FIFO. Returns None on EOF."""
        try:
            with open(self.fifo_path, "r") as f:
                for line in f:
                    stripped = line.rstrip("\n")
                    if stripped:
                        return stripped
        except (OSError, FileNotFoundError):
            pass
        return None
