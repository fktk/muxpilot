"""Timer-based polling coordination with retry backoff and cooldown."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from muxpilot.models import TmuxEvent, TmuxTree
from muxpilot.watcher import TmuxWatcher


MAX_POLL_BACKOFF_SECONDS = 30.0
DEFAULT_MAX_CONSECUTIVE_FAILURES = 5
DEFAULT_COOLDOWN_SECONDS = 2.0


class TimerCoordinator:
    """Manages periodic polling, retry backoff, and timer lifecycle.

    Decoupled from App — receives a callback instead of holding an app reference.
    """

    def __init__(
        self,
        watcher: TmuxWatcher,
        on_tick: Callable[[TmuxTree, list[TmuxEvent]], Any],
        notify_channel,
        set_interval: Callable[..., Any],
    ) -> None:
        self._watcher = watcher
        self._on_tick = on_tick
        self._notify = notify_channel
        self._set_interval = set_interval
        self._backoff = watcher.poll_interval
        self._poll_timer = None
        self._retry_timer = None
        self.cooldown_until = 0.0
        self.consecutive_failures = 0
        self.max_consecutive_failures = DEFAULT_MAX_CONSECUTIVE_FAILURES

    @property
    def backoff(self) -> float:
        return self._backoff

    @backoff.setter
    def backoff(self, value: float) -> None:
        self._backoff = value

    @property
    def poll_timer(self):
        return self._poll_timer

    @poll_timer.setter
    def poll_timer(self, value) -> None:
        self._poll_timer = value

    @property
    def retry_timer(self):
        return self._retry_timer

    @retry_timer.setter
    def retry_timer(self, value) -> None:
        self._retry_timer = value

    def start(self) -> None:
        """Start the periodic polling timer."""
        self._poll_timer = self._set_interval(
            self._watcher.poll_interval, self._on_tick_wrapper, repeat=True
        )

    def stop(self) -> None:
        """Stop all timers."""
        if self._poll_timer is not None:
            self._poll_timer.stop()
        if self._retry_timer is not None:
            self._retry_timer.stop()

    def trigger_cooldown(self, seconds: float = DEFAULT_COOLDOWN_SECONDS) -> None:
        """Suppress polling for *seconds* to avoid racing with tmux operations."""
        self.cooldown_until = time.time() + seconds

    async def tick(self) -> tuple[TmuxTree, list[TmuxEvent]] | None:
        """Execute one poll cycle with error handling and backoff.

        Returns (tree, events) on success, or None on failure / cooldown.
        """
        if time.time() < self.cooldown_until:
            return None

        try:
            tree, events = await asyncio.to_thread(self._watcher.poll)
        except Exception as e:
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.max_consecutive_failures:
                self._notify.send(
                    f"tmux polling stopped after {self.consecutive_failures} consecutive failures"
                )
                self.stop()
                return None

            if self._watcher.notify_poll_errors:
                self._notify.send(f"tmux poll failed: {e}; retrying in {self._backoff}s")
            self._backoff = min(self._backoff * 2, MAX_POLL_BACKOFF_SECONDS)
            if self._poll_timer is not None:
                self._poll_timer.pause()
            if self._retry_timer is not None:
                self._retry_timer.stop()
            self._retry_timer = self._set_interval(
                self._backoff, self._on_tick_wrapper, repeat=False
            )
            return None

        self.consecutive_failures = 0
        self._backoff = self._watcher.poll_interval
        if self._poll_timer is not None:
            self._poll_timer.resume()
        return tree, events

    async def _on_tick_wrapper(self) -> None:
        """Wrapper that calls tick() and forwards results to on_tick callback."""
        result = await self.tick()
        if result is not None:
            tree, events = result
            await self._on_tick(tree, events)
