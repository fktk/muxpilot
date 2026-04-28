# FIFO 通知チャネル実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** すべての通知を FIFO ベースの NotifyChannel 経由に統一し、外部プログラムからも `echo "msg" > ~/.muxpilot/notify` で通知を送れるようにする。

**Architecture:** 新規 `NotifyChannel` クラスが FIFO の読み取りループと `asyncio.Queue` を管理する。内部通知は `send()` で Queue に直接追加、外部通知は FIFO 経由で Queue に到達。`MuxpilotApp` は 0.5 秒ごとに Queue を消費して `self.notify()` を呼ぶ。

**Tech Stack:** Python stdlib (`os.mkfifo`, `asyncio.Queue`), Textual, pytest

---

## ファイル構成

| 操作 | ファイル | 責務 |
|------|----------|------|
| 新規 | `src/muxpilot/notify_channel.py` | FIFO ライフサイクル管理、Queue ベースのメッセージ送受信 |
| 新規 | `tests/test_notify_channel.py` | NotifyChannel の単体テスト |
| 変更 | `src/muxpilot/app.py` | NotifyChannel 統合、既存 notify 呼び出しの置き換え |
| 変更 | `tests/test_app.py` | NotifyChannel モック化対応 |
| 変更 | `tests/conftest.py` | NotifyChannel モックファクトリ追加 |

---

### Task 1: NotifyChannel — send/receive (Queue のみ)

FIFO なしで Queue の送受信だけを先に実装する。

**Files:**
- Create: `tests/test_notify_channel.py`
- Create: `src/muxpilot/notify_channel.py`

- [ ] **Step 1: send/receive の失敗するテストを書く**

`tests/test_notify_channel.py`:

```python
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
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_notify_channel.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'muxpilot.notify_channel')

- [ ] **Step 3: NotifyChannel の最小実装 (Queue のみ)**

`src/muxpilot/notify_channel.py`:

```python
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
```

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_notify_channel.py -v`
Expected: 3 passed

- [ ] **Step 5: コミット**

```bash
git add src/muxpilot/notify_channel.py tests/test_notify_channel.py
git commit -m "feat: add NotifyChannel with queue-based send/receive"
```

---

### Task 2: NotifyChannel — FIFO ライフサイクル (start/stop)

**Files:**
- Modify: `tests/test_notify_channel.py`
- Modify: `src/muxpilot/notify_channel.py`

- [ ] **Step 1: FIFO ライフサイクルの失敗するテストを書く**

`tests/test_notify_channel.py` に追加:

```python
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
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_notify_channel.py::TestFifoLifecycle -v`
Expected: FAIL (AttributeError: 'NotifyChannel' object has no attribute 'start')

- [ ] **Step 3: start/stop を実装**

`src/muxpilot/notify_channel.py` を更新。以下の import を追加し、メソッドを追加:

```python
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
```

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_notify_channel.py -v`
Expected: 6 passed

- [ ] **Step 5: コミット**

```bash
git add src/muxpilot/notify_channel.py tests/test_notify_channel.py
git commit -m "feat: add FIFO lifecycle (start/stop) to NotifyChannel"
```

---

### Task 3: NotifyChannel — FIFO 経由の外部メッセージ受信

**Files:**
- Modify: `tests/test_notify_channel.py`
- Modify: `src/muxpilot/notify_channel.py` (実装は Task 2 で完了済み、テスト追加のみ)

- [ ] **Step 1: FIFO 経由メッセージ受信の失敗するテストを書く**

`tests/test_notify_channel.py` に追加:

```python
class TestFifoRead:
    """Reading messages through FIFO from external writers."""

    @pytest.mark.asyncio
    async def test_fifo_message_reaches_queue(self, tmp_path):
        """FIFO に書き込んだメッセージが receive() で取得できる。"""
        fifo = tmp_path / "notify"
        ch = NotifyChannel(fifo_path=fifo)
        await ch.start()
        try:
            # 別スレッドで FIFO に書き込み
            def write_fifo():
                with open(fifo, "w") as f:
                    f.write("外部からの通知\n")

            await asyncio.to_thread(write_fifo)
            # 読み取りタスクが処理する時間を待つ
            await asyncio.sleep(0.3)
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
            await asyncio.sleep(0.3)
            assert ch.receive() == "msg1"
        finally:
            await ch.stop()
```

- [ ] **Step 2: テストが通ることを確認**

Run: `uv run pytest tests/test_notify_channel.py -v`
Expected: 8 passed (実装は Task 2 の `_read_loop` で済んでいるため)

もし失敗した場合は `_read_one_line` / `_read_loop` を調整する。

- [ ] **Step 3: コミット**

```bash
git add tests/test_notify_channel.py
git commit -m "test: add FIFO external message read tests"
```

---

### Task 4: conftest に NotifyChannel モックファクトリ追加

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: conftest にファクトリ関数を追加**

`tests/conftest.py` の末尾に追加:

```python
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
```

- [ ] **Step 2: コミット**

```bash
git add tests/conftest.py
git commit -m "test: add make_mock_notify_channel factory to conftest"
```

---

### Task 5: app.py に NotifyChannel を統合

**Files:**
- Modify: `src/muxpilot/app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: app.py テストの失敗するテストを書く**

`tests/test_app.py` に追加:

```python
from conftest import make_mock_notify_channel


@pytest.mark.asyncio
async def test_notify_channel_started_on_mount():
    """on_mount で NotifyChannel.start() が呼ばれること。"""
    app = _patched_app()
    mock_ch = make_mock_notify_channel()
    app._notify_channel = mock_ch
    async with app.run_test():
        mock_ch.start.assert_called_once()


@pytest.mark.asyncio
async def test_events_sent_through_notify_channel():
    """ステータス変化イベントが NotifyChannel.send() 経由で通知されること。"""
    from muxpilot.models import TmuxEvent, PaneStatus

    tree = make_tree()
    app = _patched_app(tree=tree)
    mock_ch = make_mock_notify_channel()
    app._notify_channel = mock_ch
    async with app.run_test() as pilot:
        # trigger refresh which processes events
        app.query_one("#tmux-tree").focus()
        await pilot.press("r")
        # send should have been called for the "Refreshed" message
        assert any(
            call.args[0] == "Refreshed"
            for call in mock_ch.send.call_args_list
            if call.args
        )
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_app.py::test_notify_channel_started_on_mount tests/test_app.py::test_events_sent_through_notify_channel -v`
Expected: FAIL

- [ ] **Step 3: app.py を変更 — NotifyChannel を統合**

`src/muxpilot/app.py` の変更:

import 追加:
```python
from muxpilot.notify_channel import NotifyChannel
```

`NOTIFY_CHECK_INTERVAL = 0.5` を `POLL_INTERVAL_SECONDS` の下に追加。

`__init__` に追加:
```python
self._notify_channel = NotifyChannel()
```

`on_mount` の末尾に追加:
```python
await self._notify_channel.start()
self.set_interval(NOTIFY_CHECK_INTERVAL, self._check_notifications)
```

新メソッド追加:
```python
async def _check_notifications(self) -> None:
    """Consume messages from NotifyChannel and display as Textual notifications."""
    while True:
        msg = self._notify_channel.receive()
        if msg is None:
            break
        self.notify(msg, timeout=5)
```

`on_unmount` メソッド追加:
```python
async def on_unmount(self) -> None:
    """Clean up NotifyChannel on app exit."""
    await self._notify_channel.stop()
```

すべての `self.notify(...)` 呼び出しを `self._notify_channel.send(...)` に置き換える。
ただし `_check_notifications` 内の `self.notify()` はそのまま残す。

置き換え対象:
- `_do_refresh` 内の `self.notify(f"Error fetching tmux info: {e}", severity="error")` → `self._notify_channel.send(f"Error fetching tmux info: {e}")`
- `_do_refresh` 内の `self.notify(event.message, timeout=5)` → `self._notify_channel.send(event.message)`
- `_poll_tmux` 内の `self.notify(event.message, timeout=5)` → `self._notify_channel.send(event.message)`
- `on_tmux_tree_view_pane_activated` 内の 3 つの `self.notify(...)` → `self._notify_channel.send(...)`
- `action_refresh` の `self.notify("Refreshed", timeout=2)` → `self._notify_channel.send("Refreshed")`
- `action_help` の `self.notify(...)` → `self._notify_channel.send(...)`
- `action_filter_errors` 内の 2 つの `self.notify(...)` → `self._notify_channel.send(...)`
- `action_filter_waiting` 内の 2 つの `self.notify(...)` → `self._notify_channel.send(...)`
- `action_filter_all` の `self.notify(...)` → `self._notify_channel.send(...)`

注意: `severity` や `timeout` パラメータは `send()` では不要（`_check_notifications` で統一的に `timeout=5` を使う）。

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_app.py -v`
Expected: ALL passed

- [ ] **Step 5: 全テスト実行**

Run: `uv run pytest tests/ -v`
Expected: ALL passed

- [ ] **Step 6: コミット**

```bash
git add src/muxpilot/app.py tests/test_app.py
git commit -m "feat: integrate NotifyChannel into app, unify all notifications through FIFO channel"
```

---

### Task 6: 全体確認と最終コミット

**Files:**
- All files

- [ ] **Step 1: 全テスト実行**

Run: `uv run pytest tests/ -v`
Expected: ALL passed

- [ ] **Step 2: 手動確認用メモ（tmux 環境がある場合）**

```bash
# ターミナル 1: muxpilot 起動
uv run muxpilot

# ターミナル 2: 外部通知送信
echo "テスト通知" > ~/.muxpilot/notify
```

muxpilot 画面にトースト通知「テスト通知」が表示されれば成功。

- [ ] **Step 3: 最終コミット（必要な場合のみ）**

未コミットの変更がある場合:

```bash
git add -A
git commit -m "chore: final cleanup for FIFO notify channel"
```
