"""FIFO-based notification channel for muxpilot."""

from __future__ import annotations

import queue
from pathlib import Path


DEFAULT_FIFO_PATH = Path.home() / ".muxpilot" / "notify"


class NotifyChannel:
    """Notification channel that unifies internal and external (FIFO) messages."""

    def __init__(self, fifo_path: Path = DEFAULT_FIFO_PATH) -> None:
        self.fifo_path = fifo_path
        self._queue: queue.SimpleQueue[str] = queue.SimpleQueue()

    def send(self, message: str) -> None:
        """Add a message to the notification queue (internal use)."""
        self._queue.put(message)

    def receive(self) -> str | None:
        """Get next message from the queue, or None if empty."""
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None
