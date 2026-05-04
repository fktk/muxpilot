# muxpilot UX Overhaul Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all critical UX issues identified in the critical review — robustness, visual clarity, information architecture, and workflow fit for a "command center" dashboard.

**Architecture:** Keep the existing Textual + libtmux architecture. Add a `ModalScreen` for confirmations, a `HelpScreen` for discoverability, and a `FilterStatusBar` overlay for mode indication. Harden the polling loop with exponential backoff and user-visible error recovery.

**Tech Stack:** Python 3.12+, Textual, libtmux, pytest-asyncio

---

## Milestone 1: Robustness & Safety (P0)

> These fix silent failures and data-loss risks. Must be implemented first.

---

### Task 1: Harden polling loop with retry and user-visible errors

**Problem:** `_poll_tmux` silently swallows all exceptions, causing the UI to freeze forever if tmux server hiccups.

**Files:**
- Modify: `src/muxpilot/app.py:198-225`
- Modify: `src/muxpilot/app.py:28-29` (add constants)
- Test: `tests/test_app.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_poll_tmux_shows_error_on_exception():
    """When watcher.poll raises, status bar should show error and polling continues."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])
    ])
    app = _patched_app(tree=tree)
    app._watcher.poll = MagicMock(side_effect=RuntimeError("tmux down"))
    async with app.run_test() as pilot:
        await pilot.pause(0.1)
        # After a poll tick, the error should be visible in notify channel
        assert any("tmux down" in str(m) for m in app._notify_channel._internal_messages)
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_app.py::test_poll_tmux_shows_error_on_exception -v
```
Expected: FAIL — assertion error, exception swallowed silently.

**Step 3: Implement retry + notification**

Add to `app.py` near top:
```python
MAX_POLL_BACKOFF_SECONDS = 30.0
```

In `__init__`, add:
```python
self._poll_backoff = POLL_INTERVAL_SECONDS
```

Replace `_poll_tmux`:
```python
async def _poll_tmux(self) -> None:
    try:
        tree, events = await asyncio.to_thread(self._watcher.poll)
    except Exception as e:
        self._notify_channel.send(f"tmux poll failed: {e}")
        self._poll_backoff = min(self._poll_backoff * 2, MAX_POLL_BACKOFF_SECONDS)
        self.set_interval(self._poll_backoff, self._poll_tmux, repeat=False)
        return

    self._poll_backoff = POLL_INTERVAL_SECONDS  # reset on success
    self._apply_labels(tree)
    # ... rest of existing logic ...
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_app.py::test_poll_tmux_shows_error_on_exception -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add src/muxpilot/app.py tests/test_app.py
git commit -m "fix: harden polling loop with backoff and visible errors"
```

---

### Task 2: Add KillPaneModalScreen for safe pane killing

**Problem:** `x` key kill confirmation is a notification-bar message, not a real modal. Users can accidentally confirm or the state lingers.

**Files:**
- Create: `src/muxpilot/screens/__init__.py`
- Create: `src/muxpilot/screens/kill_modal.py`
- Modify: `src/muxpilot/app.py:365-427` (replace kill logic + key handler)
- Test: `tests/test_kill_modal.py`

**Step 1: Write the failing test**

```python
import pytest
from muxpilot.screens.kill_modal import KillPaneModalScreen

@pytest.mark.asyncio
async def test_kill_modal_confirms():
    calls = []
    async def on_confirm():
        calls.append("confirm")
    screen = KillPaneModalScreen("%0", on_confirm=on_confirm)
    async with screen.run_test() as pilot:
        await pilot.press("y")
        assert "confirm" in calls
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_kill_modal.py -v
```
Expected: FAIL — module not found.

**Step 3: Implement KillPaneModalScreen**

`src/muxpilot/screens/__init__.py`:
```python
"""Textual screens for muxpilot."""
from muxpilot.screens.kill_modal import KillPaneModalScreen

__all__ = ["KillPaneModalScreen"]
```

`src/muxpilot/screens/kill_modal.py`:
```python
from __future__ import annotations

from typing import Awaitable, Callable

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class KillPaneModalScreen(ModalScreen[bool]):
    """Modal dialog to confirm pane kill."""

    DEFAULT_CSS = """
    KillPaneModalScreen {
        align: center middle;
    }
    KillPaneModalScreen > Vertical {
        width: auto;
        height: auto;
        padding: 1 2;
        border: thick $background 80%;
        background: $surface;
    }
    KillPaneModalScreen .title {
        text-align: center;
        text-style: bold;
        color: $error;
        margin-bottom: 1;
    }
    KillPaneModalScreen .pane-id {
        text-align: center;
        margin-bottom: 1;
    }
    KillPaneModalScreen Horizontal {
        width: auto;
        height: auto;
        align: center middle;
    }
    KillPaneModalScreen Button {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        pane_id: str,
        pane_label: str = "",
        on_confirm: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__()
        self.pane_id = pane_id
        self.pane_label = pane_label or pane_id
        self._on_confirm = on_confirm

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Kill Pane?", classes="title")
            yield Static(self.pane_label, classes="pane-id")
            with Horizontal():
                yield Button("Kill (y)", variant="error", id="confirm")
                yield Button("Cancel (n)", variant="primary", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def on_key(self, event) -> None:
        if event.key in ("y", "enter"):
            self.dismiss(True)
            event.stop()
        elif event.key in ("n", "escape"):
            self.dismiss(False)
            event.stop()
```

**Step 4: Wire into app.py**

Remove old kill state vars (`_kill_pane_id`, `_confirm_kill_pane`, `_cancel_kill_pane`, and the kill branch in `on_key`).

Replace `action_kill_pane`:
```python
async def action_kill_pane(self) -> None:
    tw = self.query_one("#tmux-tree", TmuxTreeView)
    node = tw.cursor_node
    if node is None or node == tw.root:
        return
    data = tw._node_data.get(node.id)
    if not data:
        return
    node_type, session, window, pane = data
    if node_type != "pane" or pane is None:
        return
    if pane.pane_id == self._current_pane_id:
        self._notify_channel.send("Cannot kill the current pane")
        return

    label = pane.custom_label or pane.pane_id
    def on_result(confirmed: bool | None) -> None:
        if confirmed:
            success = self._client.kill_pane(pane.pane_id)
            msg = f"Killed pane {label}" if success else f"Failed to kill pane {label}"
            self._notify_channel.send(msg)
            asyncio.create_task(self._do_refresh())

    self.push_screen(
        KillPaneModalScreen(pane.pane_id, label),
        on_result,
    )
```

**Step 5: Run tests**

```bash
uv run pytest tests/test_kill_modal.py tests/test_app.py -v
```
Expected: PASS

**Step 6: Commit**

```bash
git add src/muxpilot/screens/ src/muxpilot/app.py tests/test_kill_modal.py
git commit -m "feat: add KillPaneModalScreen for safe pane deletion"
```

---

### Task 3: Notify user when config file has errors

**Problem:** `watcher.py` swallows config parse/regex compile errors silently.

**Files:**
- Modify: `src/muxpilot/watcher.py:64-83`
- Modify: `src/muxpilot/app.py:101-111` (pass a callback or expose errors)
- Test: `tests/test_watcher_config.py`

**Step 1: Write the failing test**

```python
def test_watcher_config_error_raises():
    import tempfile, pathlib
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write("[watcher\n")  # invalid toml
        path = f.name
    client = make_mock_client()
    try:
        # Currently no error is raised; we want it to report.
        watcher = TmuxWatcher(client, config_path=pathlib.Path(path))
        assert watcher._config_error is not None
    finally:
        import os
        os.unlink(path)
```

**Step 2: Run test**

```bash
uv run pytest tests/test_watcher_config.py::test_watcher_config_error_raises -v
```
Expected: FAIL — `_config_error` does not exist.

**Step 3: Implement error capture**

In `watcher.py`, modify `__init__`:
```python
self._config_error: str | None = None
# ... inside try/except ...
except Exception as e:
    self._config_error = str(e)
```

Add optional `config_path` argument to `__init__` (default None → use default path).

In `app.py`, after creating watcher, check:
```python
if self._watcher._config_error:
    self._notify_channel.send(f"Config error: {self._watcher._config_error}")
```

**Step 4: Run test**

```bash
uv run pytest tests/test_watcher_config.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add src/muxpilot/watcher.py src/muxpilot/app.py tests/test_watcher_config.py
git commit -m "fix: surface config file parse/compile errors to user"
```

---

### Task 4: Warn when running outside tmux

**Problem:** `on_mount` has a comment "show a warning" but does nothing.

**Files:**
- Modify: `src/muxpilot/app.py:129-133`
- Test: `tests/test_app.py`

**Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_shows_warning_when_not_in_tmux():
    app = _patched_app()
    app._client.is_inside_tmux = MagicMock(return_value=False)
    async with app.run_test() as pilot:
        await pilot.pause(0.1)
        msgs = [str(m) for m in app._notify_channel._internal_messages]
        assert any("not inside tmux" in m.lower() for m in msgs)
```

**Step 2: Run test**

```bash
uv run pytest tests/test_app.py::test_shows_warning_when_not_in_tmux -v
```
Expected: FAIL

**Step 3: Implement**

Replace the empty `pass` in `on_mount`:
```python
if not self._client.is_inside_tmux():
    self._notify_channel.send("Warning: not running inside a tmux session")
```

**Step 4: Run test**

```bash
uv run pytest tests/test_app.py::test_shows_warning_when_not_in_tmux -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add src/muxpilot/app.py tests/test_app.py
git commit -m "fix: show warning when launched outside tmux"
```

---

## Milestone 2: Visual Clarity & Discoverability (P1)

> Make the current mode obvious and help accessible.

---

### Task 5: Add HelpScreen with full keybindings

**Problem:** `?` shows a single-line notification that scrolls away. Textual has a built-in help screen mechanism that is unused.

**Files:**
- Create: `src/muxpilot/screens/help_screen.py`
- Modify: `src/muxpilot/screens/__init__.py`
- Modify: `src/muxpilot/app.py:257-259`
- Test: `tests/test_help_screen.py`

**Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_help_screen_shows_bindings():
    from muxpilot.screens.help_screen import HelpScreen
    screen = HelpScreen()
    async with screen.run_test() as pilot:
        assert "Enter" in screen.query_one("#help-content").renderable
```

**Step 2: Run test**

```bash
uv run pytest tests/test_help_screen.py -v
```
Expected: FAIL — module not found.

**Step 3: Implement HelpScreen**

`src/muxpilot/screens/help_screen.py`:
```python
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Label, Static


class HelpScreen(ModalScreen[None]):
    """Full keybinding help modal."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    HelpScreen > Vertical {
        width: 60;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        border: thick $background 80%;
        background: $surface;
    }
    HelpScreen .title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    HelpScreen DataTable {
        height: auto;
        max-height: 1fr;
        border: none;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("muxpilot Help", classes="title")
            table = DataTable(id="help-content")
            table.add_columns("Key", "Action")
            table.add_rows([
                ("↑ / k", "Move cursor up"),
                ("↓ / j", "Move cursor down"),
                ("Enter", "Jump to selected pane"),
                ("a", "Collapse / expand all"),
                ("r", "Manual refresh"),
                ("/", "Toggle name filter"),
                ("e", "Show only error panes"),
                ("w", "Show only waiting panes"),
                ("c", "Clear all filters"),
                ("n", "Rename selected node"),
                ("x", "Kill selected pane"),
                ("?", "Show this help"),
                ("q", "Quit"),
            ])
            yield table
            yield Static("Press Esc or q to close", classes="footer")

    def on_key(self, event) -> None:
        if event.key in ("escape", "q"):
            self.dismiss()
            event.stop()
```

Update `screens/__init__.py` to export it.

Replace `action_help` in `app.py`:
```python
from muxpilot.screens.help_screen import HelpScreen

def action_help(self) -> None:
    self.push_screen(HelpScreen())
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_help_screen.py tests/test_app.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add src/muxpilot/screens/ src/muxpilot/app.py tests/test_help_screen.py
git commit -m "feat: add HelpScreen for full keybinding discoverability"
```

---

### Task 6: Add persistent filter status indicator

**Problem:** User cannot tell which filters (name, error, waiting) are currently active.

**Files:**
- Create: `src/muxpilot/widgets/filter_bar.py`
- Modify: `src/muxpilot/app.py:118-128` (compose), `action_filter_*` methods
- Test: `tests/test_filter_bar.py`

**Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_filter_bar_shows_error_filter():
    from muxpilot.widgets.filter_bar import FilterBar
    bar = FilterBar()
    async with bar.run_test():
        bar.update(status_filter={PaneStatus.ERROR}, name_filter="")
        assert "ERROR" in bar.renderable
```

**Step 2: Run test**

```bash
uv run pytest tests/test_filter_bar.py -v
```
Expected: FAIL

**Step 3: Implement FilterBar**

`src/muxpilot/widgets/filter_bar.py`:
```python
from __future__ import annotations

from textual.widgets import Static

from muxpilot.models import PaneStatus, STATUS_ICONS


class FilterBar(Static):
    """Shows currently active filters above the tree."""

    DEFAULT_CSS = """
    FilterBar {
        dock: top;
        display: none;
        height: 1;
        background: $warning-darken-2;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }
    FilterBar.-active {
        display: block;
    }
    """

    def update(self, status_filter: set[PaneStatus] | None, name_filter: str) -> None:
        parts: list[str] = []
        if name_filter:
            parts.append(f'name: "{name_filter}"')
        if status_filter:
            labels = []
            for s in status_filter:
                icon = STATUS_ICONS.get(s, "")
                labels.append(f"{icon} {s.value}")
            parts.append("  ".join(labels))
        if parts:
            self.update("Filters: " + "  │  ".join(parts))
            self.add_class("-active")
        else:
            self.update("")
            self.remove_class("-active")
```

**Step 4: Wire into app.py**

In `compose`, add `yield FilterBar(id="filter-bar")` inside `#tree-panel` Vertical, before the tree.

In `_do_refresh`, after populating tree:
```python
self.query_one("#filter-bar", FilterBar).update(self._status_filter, self._name_filter)
```

In all `action_filter_*` methods, after updating filters, refresh the bar (already covered by `_do_refresh` if we call it).

**Step 5: Run tests**

```bash
uv run pytest tests/test_filter_bar.py tests/test_app.py -v
```
Expected: PASS

**Step 6: Commit**

```bash
git add src/muxpilot/widgets/filter_bar.py src/muxpilot/app.py tests/test_filter_bar.py
git commit -m "feat: add persistent filter status bar"
```

---

### Task 7: Allow Escape to close filter input

**Problem:** Filter input opened with `/` cannot be closed with Escape.

**Files:**
- Modify: `src/muxpilot/app.py:408-427`
- Test: `tests/test_app.py`

**Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_escape_closes_filter_input():
    app = _patched_app()
    async with app.run_test() as pilot:
        await pilot.press("slash")
        assert app.query_one("#filter-input").has_class("-active")
        await pilot.press("escape")
        assert not app.query_one("#filter-input").has_class("-active")
```

**Step 2: Run test**

```bash
uv run pytest tests/test_app.py::test_escape_closes_filter_input -v
```
Expected: FAIL

**Step 3: Implement**

In `on_key`, add filter-input escape handling alongside rename-input:
```python
filter_input = self.query_one("#filter-input", Input)
if event.key == "escape" and filter_input.has_class("-active"):
    filter_input.remove_class("-active")
    filter_input.value = ""
    self._name_filter = ""
    await self._do_refresh()
    self.query_one("#tmux-tree").focus()
    event.prevent_default()
    event.stop()
```

Note: `on_key` is sync, but `_do_refresh` is async. Move the filter close into a helper or use `self.run_worker` / restructure. Simpler: make `on_key` async.

**Step 4: Run test**

```bash
uv run pytest tests/test_app.py::test_escape_closes_filter_input -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add src/muxpilot/app.py tests/test_app.py
git commit -m "fix: allow Escape to close filter input"
```

---

## Milestone 3: Information Architecture (P2)

> Clean up icons, labels, and paths.

---

### Task 8: Unify status icons (remove mixed emoji/symbols)

**Problem:** `●◌⏳🔴✅?` mixes Unicode symbols and emoji, creating inconsistent visual weight.

**Files:**
- Modify: `src/muxpilot/models.py:21-28`
- Test: `tests/test_models.py`

**Step 1: Write failing test**

```python
def test_status_icons_are_consistent():
    from muxpilot.models import STATUS_ICONS, PaneStatus
    # All should be single-char width symbols (no wide emoji)
    for status, icon in STATUS_ICONS.items():
        assert len(icon) <= 2  # allow combining chars but not surrogate pairs
```

**Step 2: Run test**

```bash
uv run pytest tests/test_models.py::test_status_icons_are_consistent -v
```
Expected: FAIL if we enforce stricter rules; currently passes but we will change values.

**Step 3: Implement unified icon set**

Replace `STATUS_ICONS`:
```python
STATUS_ICONS: dict[PaneStatus, str] = {
    PaneStatus.ACTIVE: "●",
    PaneStatus.IDLE: "○",
    PaneStatus.WAITING_INPUT: "◆",
    PaneStatus.ERROR: "▲",
    PaneStatus.COMPLETED: "■",
    PaneStatus.UNKNOWN: "?",
}
```

Update README table and any test assertions that hardcode old icons.

**Step 4: Run tests**

```bash
uv run pytest tests/test_models.py tests/test_app.py tests/test_watcher.py -v
```
Expected: PASS after updating hardcoded assertions.

**Step 5: Commit**

```bash
git add src/muxpilot/models.py tests/ README.md
git commit -m "style: unify status icons to consistent geometric symbols"
```

---

### Task 9: Improve pane label readability

**Problem:** `[cmd] path` is too long and often truncated. Full command from psutil is noisy.

**Files:**
- Modify: `src/muxpilot/models.py:47-67`
- Test: `tests/test_models.py`

**Step 1: Write failing test**

```python
def test_pane_label_uses_shortened_path():
    from muxpilot.models import PaneInfo
    p = PaneInfo(
        pane_id="%0", pane_index=0,
        current_command="zsh", current_path="/home/user/projects/muxpilot/src",
        is_active=False, width=80, height=24,
        full_command="/bin/zsh"
    )
    label = p.display_label
    assert "zsh" in label
    assert "/home/user" not in label
    assert "muxpilot/src" in label or "src" in label
```

**Step 2: Run test**

```bash
uv run pytest tests/test_models.py::test_pane_label_uses_shortened_path -v
```
Expected: FAIL — current behavior includes long path.

**Step 3: Implement smarter label**

Replace `display_label` property:
```python
@property
def display_label(self) -> str:
    icon = STATUS_ICONS.get(self.status, "?")
    if self.is_self:
        return f"{icon} muxpilot"
    if self.custom_label:
        return f"{icon} {self.custom_label}"

    # Use only the last path component unless it is too generic
    path = self.current_path.rstrip("/")
    parts = path.split("/")
    if len(parts) >= 2:
        short_path = f"{parts[-2]}/{parts[-1]}"
    else:
        short_path = parts[-1] if parts else ""

    # Prefer a concise command; skip bare shells if we have a child process
    cmd = self.full_command or self.current_command
    shell_names = {"bash", "zsh", "fish", "sh", "tmux"}
    if self.current_command in shell_names and self.full_command:
        cmd = self.full_command.split()[0].split("/")[-1] if self.full_command else self.current_command
    else:
        cmd = self.current_command or self.full_command

    return f"{icon} {cmd} — {short_path}"
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_models.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add src/muxpilot/models.py tests/test_models.py
git commit -m "feat: improve pane label readability with shorter paths and commands"
```

---

### Task 10: Document theme setting and unify data paths

**Problem:** Theme can be set via config but is undocumented. FIFO path and config path are inconsistent.

**Files:**
- Modify: `config.example.toml`
- Modify: `README.md`
- Modify: `src/muxpilot/notify_channel.py:14` (change path)

**Step 1: Decide new paths**

Config: `~/.config/muxpilot/config.toml` (keep)
FIFO: `~/.config/muxpilot/notify` (unify under same dir)

**Step 2: Update notify_channel.py**

```python
DEFAULT_FIFO_PATH = Path.home() / ".config" / "muxpilot" / "notify"
```

**Step 3: Update config.example.toml**

```toml
[app]
theme = "textual-dark"  # or "textual-light", "nord", "gruvbox"

[watcher]
# ... existing ...
```

**Step 4: Update README.md**

Add section on theme and correct FIFO path.

**Step 5: Run tests**

```bash
uv run pytest tests/test_notify_channel.py -v
```
Expected: PASS after updating any hardcoded path assertions.

**Step 6: Commit**

```bash
git add src/muxpilot/notify_channel.py config.example.toml README.md
git commit -m "docs: document theme setting and unify fifo path under config dir"
```

---

## Milestone 4: Workflow Enhancement (P2)

> Better fit for the "command center" use case.

---

### Task 11: Exclude or de-emphasize self pane in tree

**Problem:** muxpilot's own pane appears in the tree with a rocket emoji, breaking the dashboard metaphor.

**Files:**
- Modify: `src/muxpilot/widgets/tree_view.py:109-183`
- Modify: `src/muxpilot/models.py:47-67` (remove rocket)
- Test: `tests/test_tree_view.py`

**Step 1: Write failing test**

```python
def test_self_pane_hidden():
    from muxpilot.widgets.tree_view import TmuxTreeView
    from muxpilot.models import make_tree, make_session, make_window, make_pane
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0"),
            make_pane(pane_id="%1", is_self=True),
        ])])
    ])
    tw = TmuxTreeView()
    tw.populate(tree, current_pane_id="%1")
    assert "%1" not in tw._pane_map
```

**Step 2: Run test**

```bash
uv run pytest tests/test_tree_view.py::test_self_pane_hidden -v
```
Expected: FAIL

**Step 3: Implement exclusion**

In `TmuxTreeView.populate`, when iterating panes:
```python
for pane in window.panes:
    if pane.is_self:
        continue
    # ... rest ...
```

Remove `is_self` special case from `PaneInfo.display_label`.

**Step 4: Run tests**

```bash
uv run pytest tests/test_tree_view.py tests/test_models.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add src/muxpilot/widgets/tree_view.py src/muxpilot/models.py tests/test_tree_view.py
git commit -m "feat: exclude muxpilot's own pane from tree view"
```

---

### Task 12: Add "Back" navigation (return to previous pane)

**Problem:** After jumping to a pane, there is no way to return to muxpilot except via tmux prefix key. A back button/keystroke would reinforce the command-center pattern.

**Files:**
- Modify: `src/muxpilot/app.py:104` (add `_previous_pane_id`)
- Modify: `src/muxpilot/app.py:236-251` (save previous before jumping)
- Modify: `src/muxpilot/app.py:87-97` (add `b` binding)
- Test: `tests/test_app.py`

**Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_back_navigation_returns_to_previous_pane():
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0"),
            make_pane(pane_id="%1"),
        ])])
    ])
    app = _patched_app(tree=tree, current_pane_id="%0")
    async with app.run_test() as pilot:
        # Jump to %1
        await app.on_tmux_tree_view_pane_activated(
            TmuxTreeView.PaneActivated(pane_id="%1")
        )
        assert app._previous_pane_id == "%0"
        # Press b to go back
        app._client.navigate_to.reset_mock()
        await pilot.press("b")
        app._client.navigate_to.assert_called_once_with("%0")
```

**Step 2: Run test**

```bash
uv run pytest tests/test_app.py::test_back_navigation_returns_to_previous_pane -v
```
Expected: FAIL

**Step 3: Implement**

In `__init__`, add:
```python
self._previous_pane_id: str | None = None
```

In `on_tmux_tree_view_pane_activated`, before navigating:
```python
self._previous_pane_id = self._current_pane_id
```

Add binding:
```python
Binding("b", "back", "Back"),
```

Add action:
```python
async def action_back(self) -> None:
    if self._previous_pane_id:
        success = self._client.navigate_to(self._previous_pane_id)
        if success:
            self._notify_channel.send("Returned to previous pane")
            await self._do_refresh()
        else:
            self._notify_channel.send("Previous pane no longer exists")
    else:
        self._notify_channel.send("No previous pane to return to")
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_app.py::test_back_navigation_returns_to_previous_pane -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add src/muxpilot/app.py tests/test_app.py
git commit -m "feat: add back navigation with 'b' key"
```

---

### Task 13: Enable Enter on window/session to jump to active pane

**Problem:** Enter on a window or session node does nothing. Users expect it to navigate into the active child.

**Files:**
- Modify: `src/muxpilot/widgets/tree_view.py:219-225`
- Modify: `src/muxpilot/app.py:226-251`
- Test: `tests/test_app.py`

**Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_enter_on_window_navigates_to_active_pane():
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0", is_active=True),
            make_pane(pane_id="%1"),
        ])])
    ])
    app = _patched_app(tree=tree, current_pane_id="%99")
    async with app.run_test() as pilot:
        msg = TmuxTreeView.PaneActivated(pane_id="%0")
        await app.on_tmux_tree_view_pane_activated(msg)
        app._client.navigate_to.assert_called_once_with("%0")
```

(We will add logic to resolve window/session to active pane in the message handler.)

**Step 2: Run test**

```bash
uv run pytest tests/test_app.py::test_enter_on_window_navigates_to_active_pane -v
```
Expected: FAIL — currently only pane nodes emit `PaneActivated`.

**Step 3: Implement**

In `tree_view.py`, modify `on_tree_node_selected`:
```python
def on_tree_node_selected(self, event: Tree.NodeSelected[Text]) -> None:
    data = self._node_data.get(event.node.id)
    if not data:
        return
    node_type, session, window, pane = data
    if node_type == "pane" and pane is not None:
        self.post_message(self.PaneActivated(pane_id=pane.pane_id))
    elif node_type == "window" and window is not None:
        active = next((p for p in window.panes if p.is_active), None)
        if active:
            self.post_message(self.PaneActivated(pane_id=active.pane_id))
    elif node_type == "session" and session is not None:
        active_window = next((w for w in session.windows if w.is_active), None)
        if active_window:
            active_pane = next((p for p in active_window.panes if p.is_active), None)
            if active_pane:
                self.post_message(self.PaneActivated(pane_id=active_pane.pane_id))
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_app.py::test_enter_on_window_navigates_to_active_pane -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add src/muxpilot/widgets/tree_view.py tests/test_app.py
git commit -m "feat: Enter on window/session navigates to active child pane"
```

---

### Task 14: Add polling interval to config

**Problem:** `POLL_INTERVAL_SECONDS = 2.0` is hardcoded.

**Files:**
- Modify: `src/muxpilot/watcher.py`
- Modify: `src/muxpilot/app.py:23-24`
- Modify: `config.example.toml`
- Test: `tests/test_watcher_config.py`

**Step 1: Write failing test**

```python
def test_watcher_reads_poll_interval_from_config():
    import tempfile, pathlib
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write('[watcher]\npoll_interval = 0.5\n')
        path = f.name
    client = make_mock_client()
    try:
        watcher = TmuxWatcher(client, config_path=pathlib.Path(path))
        assert watcher.poll_interval == 0.5
    finally:
        import os
        os.unlink(path)
```

**Step 2: Run test**

```bash
uv run pytest tests/test_watcher_config.py::test_watcher_reads_poll_interval_from_config -v
```
Expected: FAIL

**Step 3: Implement**

In `watcher.py`, add `poll_interval` param/attr, read from config `poll_interval`.

In `app.py`, after creating watcher:
```python
self.set_interval(self._watcher.poll_interval, self._poll_tmux)
```

Remove hardcoded `POLL_INTERVAL_SECONDS` constant or keep as default.

**Step 4: Run tests**

```bash
uv run pytest tests/test_watcher_config.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add src/muxpilot/watcher.py src/muxpilot/app.py config.example.toml tests/test_watcher_config.py
git commit -m "feat: make polling interval configurable"
```

---

## Appendix: Test & Commit Policy

- **TDD:** Every task starts with a failing test.
- **Commands:** Use `uv run pytest <path> -v` for tests.
- **Commits:** One commit per task, message follows conventional commits.
- **Batch:** If multiple test files need updating for a single change (e.g., icon change), include them in the same commit.
- **Regression:** After each milestone, run full test suite:
  ```bash
  uv run pytest tests/ -v
  ```

---

**Execution Options:**

1. **Subagent-Driven (this session)** — Dispatch a fresh subagent per task, review between tasks.
2. **Parallel Session (separate)** — Open a new session with `executing-plans` skill for batch execution.

Which approach would you like to take?
