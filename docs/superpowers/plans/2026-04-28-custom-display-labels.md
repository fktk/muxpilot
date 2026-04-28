# Custom Display Labels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to rename any tmux session/window/pane in the muxpilot TUI, persisting labels to `~/.config/muxpilot/config.toml`.

**Architecture:** A new `LabelStore` class manages TOML read/write for custom labels. Models gain a `custom_label` field that `display_label` checks first. The App layer applies stored labels after each poll and provides a `n`-key rename flow using an inline `Input` widget.

**Tech Stack:** Python 3.12+, `tomllib` (stdlib read) + `tomli_w` (write), Textual, pytest

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `src/muxpilot/label_store.py` | TOML-backed label persistence (get/set/delete) |
| Create | `tests/test_label_store.py` | Unit tests for LabelStore |
| Modify | `src/muxpilot/models.py` | Add `custom_label` field to PaneInfo/WindowInfo/SessionInfo |
| Modify | `tests/test_models.py` | Tests for custom_label in display_label |
| Modify | `tests/conftest.py` | Update factory functions with `custom_label` param |
| Modify | `src/muxpilot/app.py` | Integrate LabelStore, add rename action, apply labels |
| Modify | `tests/test_app.py` | Tests for rename workflow |
| Modify | `pyproject.toml` | Add `tomli_w` dependency |

---

### Task 1: Add `tomli_w` dependency

**Files:**
- Modify: `pyproject.toml:10-13`

- [ ] **Step 1: Add tomli_w to dependencies**

`tomllib` (read) is in stdlib since Python 3.11. `tomli_w` is needed for writing TOML.

In `pyproject.toml`, add `tomli_w` to the `dependencies` list:

```toml
dependencies = [
    "libtmux>=0.40",
    "textual>=1.0",
    "tomli_w>=2.0",
]
```

- [ ] **Step 2: Install dependencies**

Run: `uv sync`
Expected: resolves and installs `tomli_w`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add tomli_w dependency for TOML writing"
```

---

### Task 2: Add `custom_label` field to models

**Files:**
- Modify: `src/muxpilot/models.py:32-94`
- Modify: `tests/conftest.py:18-76`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for custom_label on PaneInfo**

Add to `tests/test_models.py` inside `TestPaneInfoDisplayLabel`:

```python
def test_display_label_with_custom_label(self) -> None:
    """When custom_label is set, display_label should return icon + custom_label."""
    pane = make_pane(status=PaneStatus.ACTIVE, custom_label="my runner")
    icon = STATUS_ICONS[PaneStatus.ACTIVE]
    assert pane.display_label == f"{icon} my runner"

def test_display_label_custom_label_empty_uses_default(self) -> None:
    """When custom_label is empty, display_label should fall back to default."""
    pane = make_pane(
        current_command="vim",
        current_path="/home/user/project",
        status=PaneStatus.IDLE,
        custom_label="",
    )
    assert "[vim]" in pane.display_label

def test_display_label_self_pane_ignores_custom_label(self) -> None:
    """Self pane should always show [muxpilot] regardless of custom_label."""
    pane = make_pane(is_self=True, custom_label="something else")
    assert "muxpilot" in pane.display_label
    assert "something else" not in pane.display_label
```

- [ ] **Step 2: Write failing tests for custom_label on WindowInfo**

Add to `tests/test_models.py` inside `TestWindowInfoDisplayLabel`:

```python
def test_display_label_with_custom_label(self) -> None:
    """When custom_label is set, display_label should return it."""
    window = make_window(window_name="editor", is_active=True, custom_label="My Editor")
    assert window.display_label == "🪟 My Editor"

def test_display_label_custom_label_empty_uses_default(self) -> None:
    """When custom_label is empty, display_label should use default format."""
    window = make_window(window_name="editor", window_index=1, is_active=True, custom_label="")
    assert "1: editor" in window.display_label
    assert "*" in window.display_label
```

- [ ] **Step 3: Write failing tests for custom_label on SessionInfo**

Add to `tests/test_models.py` inside `TestSessionInfoDisplayLabel`:

```python
def test_display_label_with_custom_label(self) -> None:
    """When custom_label is set, display_label should return it."""
    session = make_session(session_name="work", is_attached=True, custom_label="🚀 Main")
    assert session.display_label == "📦 🚀 Main"

def test_display_label_custom_label_empty_uses_default(self) -> None:
    """When custom_label is empty, display_label should use default format."""
    session = make_session(session_name="work", is_attached=True, custom_label="")
    assert "work" in session.display_label
    assert "(attached)" in session.display_label
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/test_models.py -v -x`
Expected: FAIL — `make_pane()` / `make_window()` / `make_session()` don't accept `custom_label`

- [ ] **Step 5: Add `custom_label` field to PaneInfo and update display_label**

In `src/muxpilot/models.py`, modify `PaneInfo`:

```python
@dataclass
class PaneInfo:
    """Information about a single tmux pane."""

    pane_id: str
    pane_index: int
    current_command: str
    current_path: str
    is_active: bool
    width: int
    height: int
    status: PaneStatus = PaneStatus.UNKNOWN
    is_self: bool = False
    custom_label: str = ""

    @property
    def display_label(self) -> str:
        """Label for tree view display."""
        icon = STATUS_ICONS.get(self.status, "?")

        if self.is_self:
            return f"{icon} [muxpilot]"

        if self.custom_label:
            return f"{icon} {self.custom_label}"

        # パスを親ディレクトリとディレクトリ名の2階層に短縮
        path = self.current_path
        parts = path.rstrip("/").split("/")
        if len(parts) >= 2:
            path = f"{parts[-2]}/{parts[-1]}"
        elif len(parts) == 1 and parts[0] != "":
            path = parts[0]
            
        return f"{icon} [{self.current_command}] {path}"
```

- [ ] **Step 6: Add `custom_label` field to WindowInfo and update display_label**

In `src/muxpilot/models.py`, modify `WindowInfo`:

```python
@dataclass
class WindowInfo:
    """Information about a single tmux window."""

    window_id: str
    window_name: str
    window_index: int
    is_active: bool
    panes: list[PaneInfo] = field(default_factory=list)
    custom_label: str = ""

    @property
    def display_label(self) -> str:
        """Label for tree view display."""
        if self.custom_label:
            return f"🪟 {self.custom_label}"
        active = " *" if self.is_active else ""
        return f"🪟 {self.window_index}: {self.window_name}{active}"
```

- [ ] **Step 7: Add `custom_label` field to SessionInfo and update display_label**

In `src/muxpilot/models.py`, modify `SessionInfo`:

```python
@dataclass
class SessionInfo:
    """Information about a single tmux session."""

    session_name: str
    session_id: str
    is_attached: bool
    windows: list[WindowInfo] = field(default_factory=list)
    custom_label: str = ""

    @property
    def display_label(self) -> str:
        """Label for tree view display."""
        if self.custom_label:
            return f"📦 {self.custom_label}"
        attached = " (attached)" if self.is_attached else ""
        return f"📦 {self.session_name}{attached}"
```

- [ ] **Step 8: Update conftest factory functions**

In `tests/conftest.py`, update `make_pane()`:

```python
def make_pane(
    pane_id: str = "%0",
    pane_index: int = 0,
    current_command: str = "bash",
    current_path: str = "/home/user/project",
    is_active: bool = True,
    width: int = 80,
    height: int = 24,
    status: PaneStatus = PaneStatus.UNKNOWN,
    is_self: bool = False,
    custom_label: str = "",
) -> PaneInfo:
    """Create a PaneInfo with sensible defaults."""
    return PaneInfo(
        pane_id=pane_id,
        pane_index=pane_index,
        current_command=current_command,
        current_path=current_path,
        is_active=is_active,
        width=width,
        height=height,
        status=status,
        is_self=is_self,
        custom_label=custom_label,
    )
```

Update `make_window()`:

```python
def make_window(
    window_id: str = "@0",
    window_name: str = "editor",
    window_index: int = 0,
    is_active: bool = True,
    panes: list[PaneInfo] | None = None,
    custom_label: str = "",
) -> WindowInfo:
    """Create a WindowInfo with sensible defaults."""
    if panes is None:
        panes = [make_pane()]
    return WindowInfo(
        window_id=window_id,
        window_name=window_name,
        window_index=window_index,
        is_active=is_active,
        panes=panes,
        custom_label=custom_label,
    )
```

Update `make_session()`:

```python
def make_session(
    session_name: str = "main",
    session_id: str = "$0",
    is_attached: bool = True,
    windows: list[WindowInfo] | None = None,
    custom_label: str = "",
) -> SessionInfo:
    """Create a SessionInfo with sensible defaults."""
    if windows is None:
        windows = [make_window()]
    return SessionInfo(
        session_name=session_name,
        session_id=session_id,
        is_attached=is_attached,
        windows=windows,
        custom_label=custom_label,
    )
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `uv run pytest tests/test_models.py -v`
Expected: ALL PASS

- [ ] **Step 10: Run full test suite to verify no regressions**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 11: Commit**

```bash
git add src/muxpilot/models.py tests/conftest.py tests/test_models.py
git commit -m "feat: add custom_label field to PaneInfo/WindowInfo/SessionInfo"
```

---

### Task 3: Create LabelStore

**Files:**
- Create: `src/muxpilot/label_store.py`
- Create: `tests/test_label_store.py`

- [ ] **Step 1: Write failing tests for LabelStore**

Create `tests/test_label_store.py`:

```python
"""Tests for muxpilot.label_store — TOML-backed label persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from muxpilot.label_store import LabelStore


class TestLabelStoreGetSetDelete:
    """Basic get/set/delete operations."""

    def test_get_returns_empty_string_when_no_label(self, tmp_path: Path) -> None:
        store = LabelStore(config_path=tmp_path / "config.toml")
        assert store.get("myproject") == ""

    def test_set_and_get(self, tmp_path: Path) -> None:
        store = LabelStore(config_path=tmp_path / "config.toml")
        store.set("myproject", "🚀 Main")
        assert store.get("myproject") == "🚀 Main"

    def test_set_overwrites_existing(self, tmp_path: Path) -> None:
        store = LabelStore(config_path=tmp_path / "config.toml")
        store.set("myproject", "old")
        store.set("myproject", "new")
        assert store.get("myproject") == "new"

    def test_delete_removes_label(self, tmp_path: Path) -> None:
        store = LabelStore(config_path=tmp_path / "config.toml")
        store.set("myproject", "label")
        store.delete("myproject")
        assert store.get("myproject") == ""

    def test_delete_nonexistent_key_is_noop(self, tmp_path: Path) -> None:
        store = LabelStore(config_path=tmp_path / "config.toml")
        store.delete("nonexistent")  # should not raise

    def test_set_window_label(self, tmp_path: Path) -> None:
        store = LabelStore(config_path=tmp_path / "config.toml")
        store.set("myproject.1", "Editor")
        assert store.get("myproject.1") == "Editor"

    def test_set_pane_label(self, tmp_path: Path) -> None:
        store = LabelStore(config_path=tmp_path / "config.toml")
        store.set("myproject.1.0", "vim server")
        assert store.get("myproject.1.0") == "vim server"


class TestLabelStorePersistence:
    """File persistence tests."""

    def test_labels_persist_across_instances(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        store1 = LabelStore(config_path=config_path)
        store1.set("myproject", "persisted")

        store2 = LabelStore(config_path=config_path)
        assert store2.get("myproject") == "persisted"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        config_path = tmp_path / "subdir" / "deep" / "config.toml"
        store = LabelStore(config_path=config_path)
        store.set("test", "value")
        assert config_path.exists()

    def test_loads_existing_config_without_labels_section(self, tmp_path: Path) -> None:
        """A config.toml without [labels] should not crash."""
        config_path = tmp_path / "config.toml"
        config_path.write_text('[other]\nkey = "value"\n')
        store = LabelStore(config_path=config_path)
        assert store.get("anything") == ""

    def test_preserves_other_sections(self, tmp_path: Path) -> None:
        """Setting a label should not destroy other TOML sections."""
        config_path = tmp_path / "config.toml"
        config_path.write_text('[other]\nkey = "value"\n')
        store = LabelStore(config_path=config_path)
        store.set("myproject", "label")

        import tomllib
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        assert data["other"]["key"] == "value"
        assert data["labels"]["myproject"] == "label"


class TestLabelStoreEdgeCases:
    """Edge case handling."""

    def test_session_name_with_dots(self, tmp_path: Path) -> None:
        """Session names containing dots should work (TOML quoted keys)."""
        store = LabelStore(config_path=tmp_path / "config.toml")
        store.set("my.project", "dotted")
        assert store.get("my.project") == "dotted"

    def test_empty_label_treated_as_delete(self, tmp_path: Path) -> None:
        """Setting a label to empty string should delete it."""
        store = LabelStore(config_path=tmp_path / "config.toml")
        store.set("myproject", "something")
        store.set("myproject", "")
        assert store.get("myproject") == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_label_store.py -v -x`
Expected: FAIL — `ModuleNotFoundError: No module named 'muxpilot.label_store'`

- [ ] **Step 3: Implement LabelStore**

Create `src/muxpilot/label_store.py`:

```python
"""TOML-backed label persistence for custom display names."""

from __future__ import annotations

import tomllib
from pathlib import Path

import tomli_w


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "muxpilot" / "config.toml"


class LabelStore:
    """Reads and writes custom labels to a TOML config file.

    Labels are stored under the [labels] section with flat string keys:
      - "session_name" for sessions
      - "session_name.window_index" for windows
      - "session_name.window_index.pane_index" for panes
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self._path = config_path or DEFAULT_CONFIG_PATH
        self._data: dict = self._load()

    def get(self, key: str) -> str:
        """Return the custom label for *key*, or empty string if unset."""
        return self._data.get("labels", {}).get(key, "")

    def set(self, key: str, label: str) -> None:
        """Set (or delete if empty) a custom label and persist to disk."""
        if not label:
            self.delete(key)
            return
        self._data.setdefault("labels", {})[key] = label
        self._save()

    def delete(self, key: str) -> None:
        """Remove a custom label. No-op if key doesn't exist."""
        labels = self._data.get("labels", {})
        if key in labels:
            del labels[key]
            self._save()

    def _load(self) -> dict:
        if self._path.exists():
            with open(self._path, "rb") as f:
                return tomllib.load(f)
        return {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "wb") as f:
            tomli_w.dump(self._data, f)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_label_store.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/muxpilot/label_store.py tests/test_label_store.py
git commit -m "feat: add LabelStore for TOML-backed label persistence"
```

---

### Task 4: Integrate LabelStore into App — label application

**Files:**
- Modify: `src/muxpilot/app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write failing test for labels applied on refresh**

Add to `tests/test_app.py`:

```python
# ============================================================================
# Custom labels: applied on refresh
# ============================================================================


@pytest.mark.asyncio
async def test_labels_applied_on_refresh():
    """Custom labels from LabelStore should appear in the tree after refresh."""
    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    app = _patched_app(tree=tree)
    async with app.run_test() as pilot:
        # Set a label via the store
        app._label_store.set("work", "🚀 Main Project")
        await app.action_refresh()
        await pilot.pause()

        # Verify the session's custom_label was applied
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        for node_id, (node_type, session, window, pane) in tw._node_data.items():
            if node_type == "session" and session:
                assert session.custom_label == "🚀 Main Project"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_app.py::test_labels_applied_on_refresh -v`
Expected: FAIL — `AttributeError: 'MuxpilotApp' has no attribute '_label_store'`

- [ ] **Step 3: Add LabelStore integration and _apply_labels to App**

In `src/muxpilot/app.py`, add import at top:

```python
from muxpilot.label_store import LabelStore
```

In `MuxpilotApp.__init__()`, add after `self._notify_channel`:

```python
        self._label_store = LabelStore()
```

Add the helper method to `MuxpilotApp`:

```python
    def _apply_labels(self, tree: "TmuxTree") -> None:
        """Apply custom labels from LabelStore to the tree snapshot."""
        for session in tree.sessions:
            label = self._label_store.get(session.session_name)
            if label:
                session.custom_label = label
            for window in session.windows:
                key = f"{session.session_name}.{window.window_index}"
                label = self._label_store.get(key)
                if label:
                    window.custom_label = label
                for pane in window.panes:
                    key = f"{session.session_name}.{window.window_index}.{pane.pane_index}"
                    label = self._label_store.get(key)
                    if label:
                        pane.custom_label = label
```

In `_do_refresh()`, add `self._apply_labels(tree)` right after the `tree, events = ...` line (before `tree_widget.populate()`):

```python
    async def _do_refresh(self) -> None:
        """Fetch tmux tree and update the UI."""
        try:
            tree, events = await asyncio.to_thread(self._watcher.poll)
        except Exception as e:
            self._notify_channel.send(f"Error fetching tmux info: {e}")
            return

        self._apply_labels(tree)

        # ... rest unchanged
```

In `_poll_tmux()`, add `self._apply_labels(tree)` similarly:

```python
    async def _poll_tmux(self) -> None:
        """Periodic polling callback."""
        try:
            tree, events = await asyncio.to_thread(self._watcher.poll)
        except Exception:
            return

        self._apply_labels(tree)

        # ... rest unchanged
```

- [ ] **Step 4: Update _patched_app in test_app.py to use tmp_path LabelStore**

In `tests/test_app.py`, update the `_patched_app` helper and add `tmp_path` handling. Replace the function:

```python
def _patched_app(tree=None, current_pane_id=None, label_store=None):
    """Create a MuxpilotApp with a mocked TmuxClient/Watcher."""
    mock_client = make_mock_client(tree=tree, current_pane_id=current_pane_id)
    app = MuxpilotApp()
    app._client = mock_client
    from muxpilot.watcher import TmuxWatcher
    app._watcher = TmuxWatcher(mock_client)
    app._notify_channel = make_mock_notify_channel()
    if label_store is not None:
        app._label_store = label_store
    return app
```

Update the new test to pass a `LabelStore` with `tmp_path`:

```python
@pytest.mark.asyncio
async def test_labels_applied_on_refresh(tmp_path):
    """Custom labels from LabelStore should appear in the tree after refresh."""
    from muxpilot.label_store import LabelStore
    store = LabelStore(config_path=tmp_path / "config.toml")

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    app = _patched_app(tree=tree, label_store=store)
    async with app.run_test() as pilot:
        app._label_store.set("work", "🚀 Main Project")
        await app.action_refresh()
        await pilot.pause()

        tw = app.query_one("#tmux-tree", TmuxTreeView)
        for node_id, (node_type, session, window, pane) in tw._node_data.items():
            if node_type == "session" and session:
                assert session.custom_label == "🚀 Main Project"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_app.py::test_labels_applied_on_refresh -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/muxpilot/app.py tests/test_app.py
git commit -m "feat: integrate LabelStore into app, apply labels on refresh/poll"
```

---

### Task 5: Add rename action (n key) to App

**Files:**
- Modify: `src/muxpilot/app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write failing tests for rename workflow**

Add to `tests/test_app.py`:

```python
# ============================================================================
# Custom labels: rename action (n key)
# ============================================================================


@pytest.mark.asyncio
async def test_rename_key_shows_input(tmp_path):
    """Pressing n should show the rename input."""
    from textual.widgets import Input
    from muxpilot.label_store import LabelStore

    tree = make_tree(sessions=[
        make_session(session_name="work", windows=[
            make_window(window_name="editor", panes=[make_pane(pane_id="%0")])
        ])
    ])
    store = LabelStore(config_path=tmp_path / "config.toml")
    app = _patched_app(tree=tree, label_store=store)
    async with app.run_test() as pilot:
        # Move cursor to a pane node
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")  # session
        await pilot.press("j")  # window
        await pilot.press("j")  # pane
        await pilot.pause()

        await app.action_rename()
        await pilot.pause()

        ri = app.query_one("#rename-input", Input)
        assert ri.has_class("-active")


@pytest.mark.asyncio
async def test_rename_submit_saves_label(tmp_path):
    """Submitting a name in rename input should save it via LabelStore."""
    from textual.widgets import Input
    from muxpilot.label_store import LabelStore

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    store = LabelStore(config_path=tmp_path / "config.toml")
    app = _patched_app(tree=tree, label_store=store)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        # Navigate to pane node
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause()

        await app.action_rename()
        await pilot.pause()

        ri = app.query_one("#rename-input", Input)
        ri.value = "my test runner"
        await pilot.press("enter")
        await pilot.pause()

        assert store.get("work.0.0") == "my test runner"


@pytest.mark.asyncio
async def test_rename_empty_deletes_label(tmp_path):
    """Submitting empty string should delete the custom label."""
    from textual.widgets import Input
    from muxpilot.label_store import LabelStore

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    store = LabelStore(config_path=tmp_path / "config.toml")
    store.set("work.0.0", "old label")
    app = _patched_app(tree=tree, label_store=store)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause()

        await app.action_rename()
        await pilot.pause()

        ri = app.query_one("#rename-input", Input)
        ri.value = ""
        await pilot.press("enter")
        await pilot.pause()

        assert store.get("work.0.0") == ""


@pytest.mark.asyncio
async def test_rename_escape_cancels(tmp_path):
    """Pressing Escape during rename should cancel without saving."""
    from textual.widgets import Input
    from muxpilot.label_store import LabelStore

    tree = make_tree(sessions=[
        make_session(session_name="work", session_id="$0", windows=[
            make_window(window_name="editor", window_index=0, panes=[
                make_pane(pane_id="%0", pane_index=0),
            ])
        ])
    ])
    store = LabelStore(config_path=tmp_path / "config.toml")
    app = _patched_app(tree=tree, label_store=store)
    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        tw.focus()
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause()

        await app.action_rename()
        await pilot.pause()

        ri = app.query_one("#rename-input", Input)
        ri.value = "should not save"
        await pilot.press("escape")
        await pilot.pause()

        assert store.get("work.0.0") == ""
        assert not ri.has_class("-active")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_app.py::test_rename_key_shows_input -v -x`
Expected: FAIL

- [ ] **Step 3: Add rename Input widget and CSS to App**

In `src/muxpilot/app.py`, add the rename input widget to `compose()` and CSS.

Update CSS to add the rename-input rules (add after `#filter-input.-active`):

```python
    #rename-input {
        dock: top;
        display: none;
        margin-bottom: 1;
    }

    #rename-input.-active {
        display: block;
    }
```

In `compose()`, add the rename input inside `#tree-panel` after the filter input:

```python
            with Vertical(id="tree-panel"):
                yield Input(placeholder="Filter by name...", id="filter-input")
                yield Input(placeholder="New name (empty to reset)...", id="rename-input")
                yield TmuxTreeView(id="tmux-tree")
```

Add to BINDINGS:

```python
        Binding("n", "rename", "Rename"),
```

- [ ] **Step 4: Add rename state tracking and action_rename method**

Add instance variables to `__init__()`:

```python
        self._rename_key: str | None = None
```

Add the `action_rename()` method:

```python
    async def action_rename(self) -> None:
        """Start renaming the currently selected tree node (n key)."""
        tw = self.query_one("#tmux-tree", TmuxTreeView)
        node = tw.cursor_node
        if node is None or node == tw.root:
            return

        data = tw._node_data.get(node.id)
        if not data:
            return

        node_type, session, window, pane = data

        # Build the label store key
        if node_type == "session" and session:
            self._rename_key = session.session_name
        elif node_type == "window" and session and window:
            self._rename_key = f"{session.session_name}.{window.window_index}"
        elif node_type == "pane" and session and window and pane:
            self._rename_key = f"{session.session_name}.{window.window_index}.{pane.pane_index}"
        else:
            return

        rename_input = self.query_one("#rename-input", Input)
        # Pre-fill with current custom label if any
        rename_input.value = self._label_store.get(self._rename_key)
        rename_input.add_class("-active")
        rename_input.focus()
```

- [ ] **Step 5: Handle rename input submission and escape**

Update `on_input_submitted()` to handle rename input:

```python
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in filter or rename input."""
        if event.input.id == "filter-input":
            self.query_one("#tmux-tree").focus()
        elif event.input.id == "rename-input":
            self._finish_rename(event.value)
```

Add `_finish_rename()` and `_cancel_rename()`:

```python
    def _finish_rename(self, value: str) -> None:
        """Save the rename and close the input."""
        if self._rename_key is not None:
            if value:
                self._label_store.set(self._rename_key, value)
            else:
                self._label_store.delete(self._rename_key)
            self._rename_key = None

        rename_input = self.query_one("#rename-input", Input)
        rename_input.value = ""
        rename_input.remove_class("-active")
        self.query_one("#tmux-tree").focus()
        # Trigger a refresh to show updated labels
        asyncio.ensure_future(self._do_refresh())

    def _cancel_rename(self) -> None:
        """Cancel rename without saving."""
        self._rename_key = None
        rename_input = self.query_one("#rename-input", Input)
        rename_input.value = ""
        rename_input.remove_class("-active")
        self.query_one("#tmux-tree").focus()
```

Add Escape handling. Override `on_key` to intercept Escape when rename is active:

```python
    def on_key(self, event) -> None:
        """Handle Escape key during rename."""
        rename_input = self.query_one("#rename-input", Input)
        if event.key == "escape" and rename_input.has_class("-active"):
            self._cancel_rename()
            event.prevent_default()
            event.stop()
```

- [ ] **Step 6: Run rename tests to verify they pass**

Run: `uv run pytest tests/test_app.py -k rename -v`
Expected: ALL PASS

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add src/muxpilot/app.py tests/test_app.py
git commit -m "feat: add rename action (n key) for custom display labels"
```

---

### Task 6: Update help text and bindings documentation

**Files:**
- Modify: `src/muxpilot/app.py`

- [ ] **Step 1: Update help action text**

In `action_help()`, update the help string to include the `n` key:

```python
    def action_help(self) -> None:
        """Show help (? key)."""
        self._notify_channel.send("j/k: Navigate  Enter: Go to pane  r: Refresh  /: Filter  e: Errors  w: Waiting  c: Clear filters  a: Collapse/Expand all  n: Rename  q: Quit")
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add src/muxpilot/app.py
git commit -m "docs: add rename key to help text"
```
