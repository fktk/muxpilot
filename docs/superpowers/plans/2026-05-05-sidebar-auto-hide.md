# サイドバー自動非表示機能の実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ターミナル幅が閾値以下になったら detail-panel を非表示にし、設定ファイルで閾値を変更可能にする。

**Architecture:** Textual の `on_resize` イベントで `Resize.size.width` を監視し、`label_store.py` から読み込んだ閾値と比較して `#detail-panel` の `styles.display` を `"none"` / `"block"` に切り替える。閾値 `<= 0` は無効扱い。

**Tech Stack:** Python, Textual, pytest, tomlkit

---

### Task 1: `label_store.py` に `get_sidebar_hide_threshold()` を追加

**Files:**
- Modify: `src/muxpilot/label_store.py:45-46`
- Test: `tests/test_label_store.py`

- [ ] **Step 1: Write the failing test**

`tests/test_label_store.py` の `TestLabelStoreTreePanelMaxWidth` クラスの下に新しいテストクラスを追加する：

```python
class TestLabelStoreSidebarHideThreshold:
    """Sidebar hide threshold get operations."""

    def test_get_sidebar_hide_threshold_default(self, tmp_path: Path) -> None:
        store = LabelStore(config_path=tmp_path / "config.toml")
        assert store.get_sidebar_hide_threshold() == 80

    def test_get_sidebar_hide_threshold_from_config(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text('[ui]\nsidebar_hide_threshold = 120\n')
        store = LabelStore(config_path=config_path)
        assert store.get_sidebar_hide_threshold() == 120

    def test_get_sidebar_hide_threshold_zero_means_disabled(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text('[ui]\nsidebar_hide_threshold = 0\n')
        store = LabelStore(config_path=config_path)
        assert store.get_sidebar_hide_threshold() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_label_store.py::TestLabelStoreSidebarHideThreshold -v`

Expected: FAIL with `AttributeError: 'LabelStore' object has no attribute 'get_sidebar_hide_threshold'`

- [ ] **Step 3: Write minimal implementation**

`src/muxpilot/label_store.py` の `get_tree_panel_max_width` メソッドの直後に追加する：

```python
    def get_sidebar_hide_threshold(self) -> int:
        """Return the sidebar hide threshold or 80 default."""
        ui = self._doc.get("ui")
        if ui is None:
            return 80
        return ui.get("sidebar_hide_threshold", 80)  # type: ignore[no-any-return]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_label_store.py::TestLabelStoreSidebarHideThreshold -v`

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_label_store.py src/muxpilot/label_store.py
git commit -m "feat: add get_sidebar_hide_threshold to LabelStore"
```

---

### Task 2: `app.py` に `on_resize` ハンドラと初期判定を追加

**Files:**
- Modify: `src/muxpilot/app.py`
- Test: `tests/test_app_ui.py`

- [ ] **Step 1: Write the failing test**

`tests/test_app_ui.py` に以下のテストを追加する。ファイル末尾（`test_notify_channel_started_on_mount` の下）に追加：

```python
from textual.events import Resize
from textual.geometry import Size


@pytest.mark.asyncio
async def test_detail_panel_hidden_when_below_threshold():
    """Terminal width below threshold should hide detail-panel."""
    app = _patched_app()
    async with app.run_test() as pilot:
        detail = app.query_one("#detail-panel")
        await app.on_resize(Resize(app, Size(70, 24)))
        assert detail.styles.display == "none"


@pytest.mark.asyncio
async def test_detail_panel_shown_when_above_threshold():
    """Terminal width above threshold should show detail-panel."""
    app = _patched_app()
    async with app.run_test() as pilot:
        detail = app.query_one("#detail-panel")
        await app.on_resize(Resize(app, Size(70, 24)))
        assert detail.styles.display == "none"
        await app.on_resize(Resize(app, Size(100, 24)))
        assert detail.styles.display == "block"


@pytest.mark.asyncio
async def test_detail_panel_never_hidden_when_threshold_is_zero():
    """Threshold of 0 should disable auto-hide."""
    from pathlib import Path
    config_path = tmp_path_factory.mktemp("config") / "config.toml"
    config_path.write_text('[ui]\nsidebar_hide_threshold = 0\n')
    app = _patched_app(config_path=config_path)
    async with app.run_test() as pilot:
        detail = app.query_one("#detail-panel")
        await app.on_resize(Resize(app, Size(70, 24)))
        assert detail.styles.display == "block"
```

Wait — `tmp_path_factory` は関数スコープでは使えない。`tmp_path` fixture を使うように修正する：

```python
@pytest.mark.asyncio
async def test_detail_panel_never_hidden_when_threshold_is_zero(tmp_path):
    """Threshold of 0 should disable auto-hide."""
    config_path = tmp_path / "config.toml"
    config_path.write_text('[ui]\nsidebar_hide_threshold = 0\n')
    app = _patched_app(config_path=config_path)
    async with app.run_test() as pilot:
        detail = app.query_one("#detail-panel")
        await app.on_resize(Resize(app, Size(70, 24)))
        assert detail.styles.display == "block"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_app_ui.py::test_detail_panel_hidden_when_below_threshold -v`

Expected: FAIL with `AttributeError: 'MuxpilotApp' object has no attribute 'on_resize'`

- [ ] **Step 3: Write minimal implementation**

`src/muxpilot/app.py` に以下を追加する：

1. インポートに `Resize` を追加：

```python
from textual.events import Resize
```

2. `MuxpilotApp` クラスに `on_resize` メソッドを追加（`action_quit` の直後あたりに）：

```python
    async def on_resize(self, event: Resize) -> None:
        """Hide or show the detail panel based on terminal width."""
        threshold = self._label_store_instance.get_sidebar_hide_threshold()
        if threshold <= 0:
            return
        detail = self.query_one("#detail-panel")
        if event.size.width <= threshold:
            detail.styles.display = "none"
        else:
            detail.styles.display = "block"
```

3. `on_mount` の末尾（`await self._notify_channel.start()` の直前あたり）に、初期サイズでの判定を追加：

```python
        # Apply initial sidebar visibility based on current terminal size
        await self.on_resize(Resize(self, self.size))
```

ただし `on_mount` 内の該当箇所は以下のようになる：

```python
    async def on_mount(self) -> None:
        """Initialize the app after mounting."""
        if not self._client.is_inside_tmux():
            self._notify_channel.send("Warning: not running inside a tmux session")

        self._current_pane_id = self._client.get_current_pane_id()
        await self._ui.do_refresh()

        # Start the polling timer
        self._polling.start()

        # Set initial focus to the tree to avoid the hidden input capturing keys
        self.query_one("#tmux-tree").focus()

        # Apply tree panel max-width from config
        tree_panel = self.query_one("#tree-panel", Vertical)
        tree_panel.styles.max_width = self._label_store_instance.get_tree_panel_max_width()

        # Apply initial sidebar visibility based on current terminal size
        await self.on_resize(Resize(self, self.size))

        await self._notify_channel.start()
        self.set_interval(NOTIFY_CHECK_INTERVAL, self._ui.check_notifications)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_app_ui.py::test_detail_panel_hidden_when_below_threshold tests/test_app_ui.py::test_detail_panel_shown_when_above_threshold tests/test_app_ui.py::test_detail_panel_never_hidden_when_threshold_is_zero -v`

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_app_ui.py src/muxpilot/app.py
git commit -m "feat: auto-hide detail panel when terminal width below threshold"
```

---

### Task 3: `config.example.toml` に新しい設定例を追加

**Files:**
- Modify: `config.example.toml`

- [ ] **Step 1: Write the change**

`config.example.toml` の `[ui]` セクションの末尾（`tree_panel_max_width = 60` の直後）に追加する：

```toml
# Sidebar hide threshold in characters.
# When the terminal width is at or below this value, the detail panel (sidebar)
# is automatically hidden to give more space to the tree panel.
# Set to 0 to disable auto-hide.
# Default: 80
sidebar_hide_threshold = 80
```

- [ ] **Step 2: Commit**

```bash
git add config.example.toml
git commit -m "docs: add sidebar_hide_threshold example to config.example.toml"
```

---

### Task 4: 全テストを実行してリグレッション確認

**Files:**
- (変更なし)

- [ ] **Step 1: Run all tests**

Run: `uv run pytest tests/ -v`

Expected: All tests passing. `test_app_ui.py` と `test_label_store.py` の新規テストも含めて全て PASS。

- [ ] **Step 2: Commit（必要に応じて修正）**

テストが失敗する場合は、原因を調査して修正し再度コミットする。

---

## Self-Review Checklist

1. **Spec coverage:**
   - `label_store.py` に `get_sidebar_hide_threshold()` を追加 → Task 1 でカバー
   - `app.py` で `on_resize` イベントを監視 → Task 2 でカバー
   - 閾値 `<= 0` は無効扱い → Task 1, Task 2 のテストでカバー
   - 非表示中の DetailPanel 更新は既存挙動で安全 → 設計書に記載済み、追加実装不要
   - `config.example.toml` の更新 → Task 3 でカバー

2. **Placeholder scan:**
   - すべてのステップに具体的なコードとコマンドが含まれている → OK
   - "TBD", "TODO" 等はなし → OK

3. **Type consistency:**
   - `get_sidebar_hide_threshold` は `LabelStore` のメソッドとして定義 → Task 1 で定義、Task 2 で `self._label_store_instance.get_sidebar_hide_threshold()` として呼び出し → 一致
   - `Resize` は `textual.events.Resize`、`Size` は `textual.geometry.Size` → 正しい
