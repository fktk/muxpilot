"""Tests for muxpilot.timer_coordinator — polling backoff and timer lifecycle."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from muxpilot.timer_coordinator import TimerCoordinator
from muxpilot.watcher import DEFAULT_POLL_INTERVAL

from conftest import make_tree


def _make_coordinator(
    poll_interval=DEFAULT_POLL_INTERVAL,
    on_tick=None,
    notify=None,
    set_interval=None,
):
    watcher = MagicMock()
    watcher.poll_interval = poll_interval
    watcher.notify_poll_errors = True

    if on_tick is None:
        async def _on_tick(tree, events):
            pass
        on_tick = _on_tick

    if notify is None:
        notify = MagicMock()

    if set_interval is None:
        def _set_interval(delay, callback, repeat=True):
            timer = MagicMock()
            timer.delay = delay
            timer.repeat = repeat
            return timer
        set_interval = _set_interval

    return TimerCoordinator(
        watcher=watcher,
        on_tick=on_tick,
        notify_channel=notify,
        set_interval=set_interval,
    )


class TestTimerLifecycle:
    """Tests for start/stop timer management."""

    def test_start_creates_poll_timer(self):
        set_interval = MagicMock()
        tc = _make_coordinator(set_interval=set_interval)
        tc.start()
        set_interval.assert_called_once_with(
            DEFAULT_POLL_INTERVAL, tc._on_tick_wrapper, repeat=True
        )

    def test_stop_stops_timers(self):
        poll_timer = MagicMock()
        retry_timer = MagicMock()
        set_interval = MagicMock(side_effect=[poll_timer, retry_timer])

        tc = _make_coordinator(set_interval=set_interval)
        tc.start()
        tc._retry_timer = retry_timer
        tc.stop()

        poll_timer.stop.assert_called_once()
        retry_timer.stop.assert_called_once()


class TestTick:
    """Tests for tick() — the core polling cycle."""

    @pytest.mark.asyncio
    async def test_tick_returns_tree_on_success(self):
        tree = make_tree()
        watcher = MagicMock()
        watcher.poll_interval = DEFAULT_POLL_INTERVAL
        watcher.poll.return_value = (tree, [])

        tc = TimerCoordinator(
            watcher=watcher,
            on_tick=lambda t, e: None,
            notify_channel=MagicMock(),
            set_interval=MagicMock(),
        )
        result = await tc.tick()
        assert result == (tree, [])

    @pytest.mark.asyncio
    async def test_tick_returns_none_on_cooldown(self):
        tc = _make_coordinator()
        tc.trigger_cooldown(60.0)
        result = await tc.tick()
        assert result is None

    @pytest.mark.asyncio
    async def test_tick_backoff_doubles_on_failure(self):
        watcher = MagicMock()
        watcher.poll_interval = DEFAULT_POLL_INTERVAL
        watcher.poll.side_effect = RuntimeError("tmux down")
        watcher.notify_poll_errors = True

        set_interval = MagicMock(return_value=MagicMock())
        notify = MagicMock()

        tc = TimerCoordinator(
            watcher=watcher,
            on_tick=lambda t, e: None,
            notify_channel=notify,
            set_interval=set_interval,
        )
        assert tc.backoff == DEFAULT_POLL_INTERVAL
        await tc.tick()
        assert tc.backoff == DEFAULT_POLL_INTERVAL * 2

    @pytest.mark.asyncio
    async def test_tick_backoff_caps_at_max(self):
        watcher = MagicMock()
        watcher.poll_interval = DEFAULT_POLL_INTERVAL
        watcher.poll.side_effect = RuntimeError("tmux down")
        watcher.notify_poll_errors = True

        set_interval = MagicMock(return_value=MagicMock())

        tc = TimerCoordinator(
            watcher=watcher,
            on_tick=lambda t, e: None,
            notify_channel=MagicMock(),
            set_interval=set_interval,
        )
        tc._backoff = 28.0  # Just under MAX (30)
        await tc.tick()
        assert tc.backoff == 30.0

    @pytest.mark.asyncio
    async def test_tick_stops_after_max_failures(self):
        watcher = MagicMock()
        watcher.poll_interval = DEFAULT_POLL_INTERVAL
        watcher.poll.side_effect = RuntimeError("tmux down")
        watcher.notify_poll_errors = True

        set_interval = MagicMock(return_value=MagicMock())
        notify = MagicMock()

        tc = TimerCoordinator(
            watcher=watcher,
            on_tick=lambda t, e: None,
            notify_channel=notify,
            set_interval=set_interval,
        )
        tc.max_consecutive_failures = 3

        for _ in range(3):
            await tc.tick()

        notify.send.assert_called_with("tmux polling stopped after 3 consecutive failures")

    @pytest.mark.asyncio
    async def test_tick_resets_backoff_on_success(self):
        tree = make_tree()
        watcher = MagicMock()
        watcher.poll_interval = DEFAULT_POLL_INTERVAL
        watcher.poll.side_effect = [
            RuntimeError("tmux down"),
            (tree, []),
        ]
        watcher.notify_poll_errors = True

        set_interval = MagicMock(return_value=MagicMock())

        tc = TimerCoordinator(
            watcher=watcher,
            on_tick=lambda t, e: None,
            notify_channel=MagicMock(),
            set_interval=set_interval,
        )
        await tc.tick()  # fails
        assert tc.backoff == DEFAULT_POLL_INTERVAL * 2
        await tc.tick()  # recovers
        assert tc.backoff == DEFAULT_POLL_INTERVAL

    @pytest.mark.asyncio
    async def test_tick_does_not_notify_when_disabled(self):
        watcher = MagicMock()
        watcher.poll_interval = DEFAULT_POLL_INTERVAL
        watcher.poll.side_effect = RuntimeError("tmux down")
        watcher.notify_poll_errors = False

        notify = MagicMock()
        tc = TimerCoordinator(
            watcher=watcher,
            on_tick=lambda t, e: None,
            notify_channel=notify,
            set_interval=MagicMock(return_value=MagicMock()),
        )
        await tc.tick()
        assert not any("tmux down" in str(call) for call in notify.send.call_args_list)


class TestCooldown:
    """Tests for cooldown behavior."""

    def test_trigger_cooldown_sets_future_time(self):
        tc = _make_coordinator()
        import time
        before = time.time()
        tc.trigger_cooldown(5.0)
        after = time.time()
        assert before + 5.0 <= tc.cooldown_until <= after + 5.0

    @pytest.mark.asyncio
    async def test_cooldown_skips_polling(self):
        watcher = MagicMock()
        watcher.poll_interval = DEFAULT_POLL_INTERVAL
        tc = TimerCoordinator(
            watcher=watcher,
            on_tick=lambda t, e: None,
            notify_channel=MagicMock(),
            set_interval=MagicMock(),
        )
        tc.trigger_cooldown(60.0)
        result = await tc.tick()
        assert result is None
        watcher.poll.assert_not_called()
