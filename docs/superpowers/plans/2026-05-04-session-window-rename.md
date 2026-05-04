# session/window リネーム対応（n キー）実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** tree view で session / window / pane のいずれが選択されていても `n` キーでリネームできるようにする

**Architecture:** `PaneTitleManager` を `NodeRenameManager` に拡張し、`node_type` に応じて `TmuxClient` の異なるメソッドを呼び出す。UI 層の変更はクラス名・インポートの更新のみ。

**Tech Stack:** Python, Textual, libtmux, pytest

---

## ファイル構成

| ファイル | 変更内容 |
|---------|---------|
| `src/muxpilot/tmux_client.py` | `rename_window()`, `rename_session()` を追加 |
| `src/muxpilot/controllers.py` | `PaneTitleManager` → `NodeRenameManager` にリネーム・拡張 |
| `src/muxpilot/app.py` | `PaneTitleManager` のインポート・参照を `NodeRenameManager` に変更 |
| `src/muxpilot/app_actions.py` | 同上 |
| `src/muxpilot/app_ui.py` | 同上 |
| `tests/test_tmux_client.py` | `rename_window` / `rename_session` のテストを追加 |
| `tests/test_pane_title_manager.py` → `tests/test_node_rename_manager.py` | クラス名変更、session/window のテストを追加 |
| `tests/_test_app_common.py` | `PaneTitleManager` を `NodeRenameManager` に変更 |
| `tests/test_app_rename.py` | session / window 選択時の統合テストを追加 |

---

### Task 1: TmuxClient に rename_window / rename_session を追加

**Files:**
- Modify: `src/muxpilot/tmux_client.py`
- Test: `tests/test_tmux_client.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_tmux_client.py` に以下を追加:

```python
    def test_rename_window_calls_tmux(self):
        mock_server = MagicMock()
        with patch("muxpilot.tmux_client.libtmux.Server", return_value=mock_server):
            c = TmuxClient()
            result = c.rename_window("@1", "new-window")
        mock_server.cmd.assert_called_once_with("rename-window", "-t", "@1", "new-window")
        assert result is True

    def test_rename_window_failure(self):
        import libtmux.exc
        mock_server = MagicMock()
        mock_server.cmd.side_effect = libtmux.exc.LibTmuxException("fail")
        with patch("muxpilot.tmux_client.libtmux.Server", return_value=mock_server):
            c = TmuxClient()
            result = c.rename_window("@99", "x")
        assert result is False

    def test_rename_session_calls_tmux(self):
        mock_server = MagicMock()
        with patch("muxpilot.tmux_client.libtmux.Server", return_value=mock_server):
            c = TmuxClient()
            result = c.rename_session("$1", "new-session")
        mock_server.cmd.assert_called_once_with("rename-session", "-t", "$1", "new-session")
        assert result is True

    def test_rename_session_failure(self):
        import libtmux.exc
        mock_server = MagicMock()
        mock_server.cmd.side_effect = libtmux.exc.LibTmuxException("fail")
        with patch("muxpilot.tmux_client.libtmux.Server", return_value=mock_server):
            c = TmuxClient()
            result = c.rename_session("$99", "x")
        assert result is False
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_tmux_client.py::TestPaneTitleAndGit::test_rename_window_calls_tmux -v`
Expected: FAIL — `AttributeError: 'TmuxClient' object has no attribute 'rename_window'`

- [ ] **Step 3: 最小限の実装を書く**

`src/muxpilot/tmux_client.py` の `set_pane_title` の下に追加:

```python
    def rename_window(self, window_id: str, name: str) -> bool:
        """Rename a tmux window."""
        server = libtmux.Server()
        try:
            server.cmd("rename-window", "-t", window_id, name)
            return True
        except Exception:
            return False

    def rename_session(self, session_id: str, name: str) -> bool:
        """Rename a tmux session."""
        server = libtmux.Server()
        try:
            server.cmd("rename-session", "-t", session_id, name)
            return True
        except Exception:
            return False
```

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_tmux_client.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add src/muxpilot/tmux_client.py tests/test_tmux_client.py
git commit -m "feat: add rename_window and rename_session to TmuxClient"
```

---

### Task 2: PaneTitleManager → NodeRenameManager に拡張

**Files:**
- Modify: `src/muxpilot/controllers.py`
- Rename/Modify: `tests/test_pane_title_manager.py` → `tests/test_node_rename_manager.py`

- [ ] **Step 1: 失敗するテストを書く（既存テストをベースに拡張）**

`tests/test_pane_title_manager.py` を `tests/test_node_rename_manager.py` にリネームし、内容を以下に置き換える:

```python
"""Tests for muxpilot.controllers.NodeRenameManager."""

from __future__ import annotations

from unittest.mock import MagicMock

from muxpilot.controllers import NodeRenameManager
from muxpilot.models import SessionInfo, WindowInfo, PaneInfo


def make_node_data(node_type: str, session_name="work", window_index=0, pane_index=0):
    """Create node_data tuple for NodeRenameManager.start()."""
    session = SessionInfo(
        session_name=session_name,
        session_id="$0",
        is_attached=True,
        windows=[],
    )
    window = WindowInfo(
        window_id="@0",
        window_name="editor",
        window_index=window_index,
        is_active=True,
        panes=[],
    )
    pane = PaneInfo(
        pane_id="%0",
        pane_index=pane_index,
        current_command="bash",
        current_path="/home/user",
        is_active=True,
        width=80,
        height=24,
        pane_title="",
    )
    return (node_type, session, window, pane)


class TestPaneRename:
    def test_start_returns_pane_title(self) -> None:
        client = MagicMock()
        ctrl = NodeRenameManager(client)
        data = make_node_data("pane", session_name="myproject", window_index=2, pane_index=1)
        data[3].pane_title = "existing-title"
        current = ctrl.start(data)
        assert ctrl.key == "myproject.2.1"
        assert ctrl._target_id == "%0"
        assert current == "existing-title"

    def test_start_none_returns_none(self) -> None:
        client = MagicMock()
        ctrl = NodeRenameManager(client)
        assert ctrl.start(None) is None

    def test_finish_calls_set_pane_title(self) -> None:
        client = MagicMock()
        client.set_pane_title.return_value = True
        ctrl = NodeRenameManager(client)
        ctrl.start(make_node_data("pane", session_name="work"))
        result = ctrl.finish("New Title")
        assert result == "work.0.0"
        client.set_pane_title.assert_called_once_with("%0", "New Title")

    def test_finish_empty_calls_set_pane_title(self) -> None:
        client = MagicMock()
        client.set_pane_title.return_value = True
        ctrl = NodeRenameManager(client)
        ctrl.start(make_node_data("pane", session_name="work"))
        result = ctrl.finish("")
        assert result == "work.0.0"
        client.set_pane_title.assert_called_once_with("%0", "")

    def test_finish_without_start_is_noop(self) -> None:
        client = MagicMock()
        ctrl = NodeRenameManager(client)
        assert ctrl.finish("x") is None
        client.set_pane_title.assert_not_called()

    def test_cancel_clears_key_without_saving(self) -> None:
        client = MagicMock()
        ctrl = NodeRenameManager(client)
        ctrl.start(make_node_data("pane", session_name="work"))
        ctrl.cancel()
        assert ctrl.key is None
        assert ctrl._target_id is None


class TestWindowRename:
    def test_start_returns_window_name(self) -> None:
        client = MagicMock()
        ctrl = NodeRenameManager(client)
        data = make_node_data("window", session_name="myproject", window_index=2)
        data[2].window_name = "existing-window"
        current = ctrl.start(data)
        assert ctrl.key == "myproject.2"
        assert ctrl._target_id == "@0"
        assert current == "existing-window"

    def test_finish_calls_rename_window(self) -> None:
        client = MagicMock()
        client.rename_window.return_value = True
        ctrl = NodeRenameManager(client)
        ctrl.start(make_node_data("window", session_name="work"))
        result = ctrl.finish("New Window")
        assert result == "work.0"
        client.rename_window.assert_called_once_with("@0", "New Window")

    def test_finish_empty_calls_rename_window(self) -> None:
        """Empty string is allowed for windows (tmux reverts to auto-naming)."""
        client = MagicMock()
        client.rename_window.return_value = True
        ctrl = NodeRenameManager(client)
        ctrl.start(make_node_data("window", session_name="work"))
        result = ctrl.finish("")
        assert result == "work.0"
        client.rename_window.assert_called_once_with("@0", "")


class TestSessionRename:
    def test_start_returns_session_name(self) -> None:
        client = MagicMock()
        ctrl = NodeRenameManager(client)
        data = make_node_data("session", session_name="myproject")
        current = ctrl.start(data)
        assert ctrl.key == "myproject"
        assert ctrl._target_id == "$0"
        assert current == "myproject"

    def test_finish_calls_rename_session(self) -> None:
        client = MagicMock()
        client.rename_session.return_value = True
        ctrl = NodeRenameManager(client)
        ctrl.start(make_node_data("session", session_name="work"))
        result = ctrl.finish("New Session")
        assert result == "work"
        client.rename_session.assert_called_once_with("$0", "New Session")

    def test_finish_empty_ignored_for_session(self) -> None:
        """Empty string is ignored for sessions (tmux does not allow empty session names)."""
        client = MagicMock()
        client.rename_session.return_value = True
        ctrl = NodeRenameManager(client)
        ctrl.start(make_node_data("session", session_name="work"))
        result = ctrl.finish("")
        assert result is None
        client.rename_session.assert_not_called()


class TestApplyIsNoop:
    def test_apply_is_noop(self) -> None:
        from muxpilot.models import TmuxTree
        from conftest import make_session, make_window, make_pane

        tree = TmuxTree(sessions=[
            make_session(session_name="work", session_id="$0", windows=[
                make_window(window_name="editor", window_index=0, panes=[
                    make_pane(pane_id="%0", pane_index=0),
                ])
            ])
        ])

        client = MagicMock()
        ctrl = NodeRenameManager(client)
        ctrl.apply(tree)

        assert tree.sessions[0].custom_label == ""
        assert tree.sessions[0].windows[0].custom_label == ""
        assert tree.sessions[0].windows[0].panes[0].custom_label == ""
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_node_rename_manager.py -v`
Expected: FAIL — `ImportError: cannot import name 'NodeRenameManager'` および各 `AttributeError`

- [ ] **Step 3: 最小限の実装を書く**

`src/muxpilot/controllers.py` を以下の内容に置き換える:

```python
"""Controllers extracted from MuxpilotApp to reduce its responsibilities."""

from __future__ import annotations

from dataclasses import dataclass

from muxpilot.models import PaneStatus, TmuxTree


@dataclass(frozen=True)
class FilterState:
    """Immutable filter criteria. Use replace() to create modified copies."""

    status_filter: set[PaneStatus] | None = None
    name_filter: str = ""

    def cleared(self) -> FilterState:
        """Return a new FilterState with all filters removed."""
        return FilterState(status_filter=None, name_filter="")

    def with_status(self, status: set[PaneStatus] | None) -> FilterState:
        """Return a new FilterState with the given status filter."""
        return FilterState(status_filter=status, name_filter=self.name_filter)

    def with_name(self, name: str) -> FilterState:
        """Return a new FilterState with the given name filter."""
        return FilterState(status_filter=self.status_filter, name_filter=name)


class NodeRenameManager:
    """Manages the in-progress rename operation for a tree node.

    Supports pane, window, and session renaming via TmuxClient.
    """

    def __init__(self, client=None) -> None:
        self._client = client
        self._key: str | None = None
        self._target_id: str | None = None
        self._node_type: str | None = None

    @property
    def key(self) -> str | None:
        return self._key

    @key.setter
    def key(self, value: str | None) -> None:
        self._key = value

    def start(self, node_data: tuple[str, ...] | None) -> str | None:
        """Begin a rename for the given node data.

        Returns the current name (or empty string) if a rename can
        start, or None if the node data does not support renaming.
        """
        if node_data is None:
            return None
        node_type, session, window, pane = node_data
        if node_type == "pane" and session and window and pane:
            self._key = f"{session.session_name}.{window.window_index}.{pane.pane_index}"
            self._target_id = pane.pane_id
            self._node_type = "pane"
            return pane.pane_title
        elif node_type == "window" and session and window:
            self._key = f"{session.session_name}.{window.window_index}"
            self._target_id = window.window_id
            self._node_type = "window"
            return window.window_name
        elif node_type == "session" and session:
            self._key = session.session_name
            self._target_id = session.session_id
            self._node_type = "session"
            return session.session_name
        return None

    def finish(self, value: str) -> str | None:
        """Commit the rename and return the affected key, or None."""
        key = self._key
        if key is None or self._client is None:
            return None
        if self._node_type == "pane":
            self._client.set_pane_title(self._target_id or "", value)
        elif self._node_type == "window":
            self._client.rename_window(self._target_id or "", value)
        elif self._node_type == "session":
            if not value:
                self._key = None
                self._target_id = None
                self._node_type = None
                return None
            self._client.rename_session(self._target_id or "", value)
        self._key = None
        self._target_id = None
        self._node_type = None
        return key

    def cancel(self) -> None:
        """Abort the rename without saving."""
        self._key = None
        self._target_id = None
        self._node_type = None

    def apply(self, tree: TmuxTree) -> None:
        """No-op: names come from tmux directly on next poll."""
        pass
```

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_node_rename_manager.py -v`
Expected: PASS

- [ ] **Step 5: 古いテストファイルを削除しコミット**

```bash
git rm tests/test_pane_title_manager.py
git add src/muxpilot/controllers.py tests/test_node_rename_manager.py
git commit -m "feat: extend PaneTitleManager to NodeRenameManager for session/window/pane"
```

---

### Task 3: app 層の PaneTitleManager 参照を NodeRenameManager に更新

**Files:**
- Modify: `src/muxpilot/app.py`, `src/muxpilot/app_actions.py`, `src/muxpilot/app_ui.py`, `tests/_test_app_common.py`

- [ ] **Step 1: 各ファイルのインポート・参照を更新**

`src/muxpilot/app.py` の変更:
- `from muxpilot.controllers import FilterState, PaneTitleManager` → `from muxpilot.controllers import FilterState, NodeRenameManager`
- `self._rename_controller = PaneTitleManager(self._client)` → `self._rename_controller = NodeRenameManager(self._client)`

`src/muxpilot/app_actions.py` の変更:
- インポートに `NodeRenameManager` を追加（もしあれば）。ない場合は変更なし（直接クラス名を参照していない）。
- 実際には `app_actions.py` は `_app._rename_controller` を通じて間接的に使用しているので、コード変更は不要（インポートも `controllers` モジュールから直接参照していない）。

`src/muxpilot/app_ui.py` の変更:
- 同上。間接使用なのでコード変更は不要。

`tests/_test_app_common.py` の変更:
- `from muxpilot.controllers import PaneTitleManager` → `from muxpilot.controllers import NodeRenameManager`
- `app._rename_controller = PaneTitleManager(mock_client)` → `app._rename_controller = NodeRenameManager(mock_client)`

- [ ] **Step 2: 既存の app 統合テストが通ることを確認**

Run: `uv run pytest tests/test_app_rename.py -v`
Expected: PASS

- [ ] **Step 3: コミット**

```bash
git add src/muxpilot/app.py tests/_test_app_common.py
git commit -m "refactor: update app layer to use NodeRenameManager"
```

---

### Task 4: test_app_rename.py に session / window の統合テストを追加

**Files:**
- Modify: `tests/test_app_rename.py`

- [ ] **Step 1: 失敗するテストを追加**

`tests/test_app_rename.py` の末尾に追加:

```python

@pytest.mark.asyncio
async def test_rename_window_key_shows_input():
    """Pressing n on a window node should show the rename input with window name."""
    from textual.widgets import Input

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")  # session
        await pilot.press("j")  # window
        await pilot.pause()

        await app.action_rename()
        await pilot.pause()

        ri = app.query_one("#rename-input", Input)
        assert ri.has_class("-active")
        assert ri.value == "editor"


@pytest.mark.asyncio
async def test_rename_window_submit_calls_rename_window():
    """Submitting a name for window should call rename_window on the client."""
    from textual.widgets import Input

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, window_id="@0", panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause()

        await app.action_rename()
        await pilot.pause()

        ri = app.query_one("#rename-input", Input)
        ri.value = "new-editor"
        await pilot.press("enter")
        await pilot.pause()

        app._client.rename_window.assert_called_once_with("@0", "new-editor")


@pytest.mark.asyncio
async def test_rename_session_key_shows_input():
    """Pressing n on a session node should show the rename input with session name."""
    from textual.widgets import Input

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")  # session
        await pilot.pause()

        await app.action_rename()
        await pilot.pause()

        ri = app.query_one("#rename-input", Input)
        assert ri.has_class("-active")
        assert ri.value == "work"


@pytest.mark.asyncio
async def test_rename_session_submit_calls_rename_session():
    """Submitting a name for session should call rename_session on the client."""
    from textual.widgets import Input

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")
        await pilot.pause()

        await app.action_rename()
        await pilot.pause()

        ri = app.query_one("#rename-input", Input)
        ri.value = "new-work"
        await pilot.press("enter")
        await pilot.pause()

        app._client.rename_session.assert_called_once_with("$0", "new-work")


@pytest.mark.asyncio
async def test_rename_session_empty_ignored():
    """Submitting empty string for session should NOT call rename_session."""
    from textual.widgets import Input

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")
        await pilot.pause()

        await app.action_rename()
        await pilot.pause()

        ri = app.query_one("#rename-input", Input)
        ri.value = ""
        await pilot.press("enter")
        await pilot.pause()

        app._client.rename_session.assert_not_called()
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_app_rename.py::test_rename_window_key_shows_input -v`
Expected: FAIL — `AssertionError` (value が空 or クラスがアクティブでない、あるいは rename_window メソッドがない)

実際には Task 3 まで終わっているので、テストは PASS するはず。
確認のため失敗するテストを先に実行して、現状が PASS することを確認しても良い。

- [ ] **Step 3: テストが通ることを確認（統合テスト含む）**

Run: `uv run pytest tests/test_app_rename.py -v`
Expected: PASS

- [ ] **Step 4: コミット**

```bash
git add tests/test_app_rename.py
git commit -m "test: add session/window rename integration tests"
```

---

### Task 5: 全テストスイートを実行

- [ ] **Step 1: 全テスト実行**

Run: `uv run pytest tests/ -v`
Expected: 全テスト PASS

- [ ] **Step 2: 最終コミット（任意）**

```bash
git commit --allow-empty -m "feat: session and window rename support via n key"
```

---

## セルフレビュー

- **Spec coverage:**
  - session / window / pane の `n` キーリネーム → Task 2, 3, 4 でカバー
  - 空文字列の扱い（session は無視、window/pane は送信）→ Task 2, 4 でカバー
  - `TmuxClient` の新メソッド → Task 1 でカバー
  - 既存テストの維持 → 各 Task で確認

- **Placeholder scan:** なし（TODO/TBD なし、全コードブロックに実装あり）

- **Type consistency:** `NodeRenameManager` のインターフェースは `start()` / `finish()` / `cancel()` のまま。`_pane_id` → `_target_id` に変更。

- **注意点:** `tests/test_pane_title_manager.py` はリネーム（新規作成＋削除）される。Git の追跡が正しく行われるよう `git rm` と `git add` を両方行う。
