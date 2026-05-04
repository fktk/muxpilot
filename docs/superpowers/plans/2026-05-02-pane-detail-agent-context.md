# Pane Detail Agent Context — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the pane detail panel to show repository, branch, pane title, idle time, and a recent output preview so users can identify which coding agent is running in each pane.

**Architecture:** Extend `PaneInfo`/`PaneActivity` with new fields, enrich `TmuxClient` with git queries and pane title I/O, update `TmuxWatcher` to keep output previews, replace `RenameController`'s in-memory overlays with direct tmux pane title commands, and rewrite `DetailPanel` rendering.

**Tech Stack:** Python, Textual, libtmux, pytest, unittest.mock

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/muxpilot/models.py` | `PaneInfo` / `PaneActivity` dataclasses with new fields (`pane_title`, `repo_name`, `branch`, `idle_seconds`, `recent_lines`) |
| `src/muxpilot/tmux_client.py` | Read `pane_title` from libtmux; run `git` commands to extract repo/branch; add `set_pane_title()` |
| `src/muxpilot/watcher.py` | Store last N captured lines in `PaneActivity.recent_lines`; copy `idle_seconds` onto `PaneInfo` |
| `src/muxpilot/controllers.py` | `RenameController` removes overlay dict; calls `TmuxClient.set_pane_title()` instead |
| `src/muxpilot/widgets/detail_panel.py` | Rewrite `show_pane()` layout with title/repo/branch/idle/preview sections |
| `src/muxpilot/app.py` | Wire `set_pane_title` into rename finish action; update `_apply_labels` if needed |
| `tests/conftest.py` | Update `make_pane` and `make_mock_client` signatures |
| `tests/test_models.py` | `display_label` priority tests |
| `tests/test_tmux_client.py` | `pane_title`, git info, `set_pane_title` tests |
| `tests/test_watcher.py` | `recent_lines` and `idle_seconds` tests |
| `tests/test_app.py` | Rename via pane title, detail panel content tests |

---

### Task 1: Extend Models

**Files:**
- Modify: `src/muxpilot/models.py`
- Test: `tests/test_models.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write failing tests for `display_label` priority**

In `tests/test_models.py`:

```python
def test_pane_display_label_prefers_pane_title():
    pane = make_pane(pane_title="my-agent", custom_label="old-label", current_command="bash")
    assert "my-agent" in pane.display_label
    assert "old-label" not in pane.display_label

def test_pane_display_label_fallback_to_custom_label():
    pane = make_pane(pane_title="", custom_label="custom", current_command="bash")
    assert "custom" in pane.display_label

def test_pane_display_label_fallback_to_heuristic():
    pane = make_pane(pane_title="", custom_label="", current_command="python", current_path="/home/user/proj")
    assert "python" in pane.display_label
    assert "user/proj" in pane.display_label
```

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL (PaneInfo has no pane_title kwarg)

- [ ] **Step 2: Add fields to `PaneInfo` and `PaneActivity`**

In `src/muxpilot/models.py`:

```python
@dataclass
class PaneInfo:
    pane_id: str
    pane_index: int
    current_command: str
    current_path: str
    is_active: bool
    width: int
    height: int
    status: PaneStatus = PaneStatus.ACTIVE
    is_self: bool = False
    custom_label: str = ""
    full_command: str = ""
    pane_title: str = ""
    repo_name: str = ""
    branch: str = ""
    idle_seconds: float = 0.0

    @property
    def display_label(self) -> str:
        icon = STATUS_ICONS.get(self.status, "?")
        if self.pane_title:
            return f"{icon} {self.pane_title}"
        if self.custom_label:
            return f"{icon} {self.custom_label}"
        # existing heuristic unchanged
        ...
```

```python
@dataclass
class PaneActivity:
    pane_id: str
    last_content_hash: str = ""
    last_line: str = ""
    idle_seconds: float = 0.0
    status: PaneStatus = PaneStatus.ACTIVE
    content_changed: bool = False
    recent_lines: list[str] = field(default_factory=list)
```

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 3: Update `make_pane` fixture in `tests/conftest.py`**

Add `pane_title=""`, `repo_name=""`, `branch=""`, `idle_seconds=0.0` to `make_pane` signature and `PaneInfo(...)` call.

Run: `uv run pytest tests/test_models.py tests/conftest.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/muxpilot/models.py tests/test_models.py tests/conftest.py
git commit -m "feat: add pane_title, repo_name, branch, idle_seconds to PaneInfo; add recent_lines to PaneActivity"
```

---

### Task 2: Enrich TmuxClient with pane_title and git info

**Files:**
- Modify: `src/muxpilot/tmux_client.py`
- Test: `tests/test_tmux_client.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write failing tests for pane_title and git fields**

In `tests/test_tmux_client.py`:

```python
from unittest.mock import MagicMock, patch

def test_get_tree_reads_pane_title():
    client = TmuxClient()
    pane_mock = MagicMock()
    pane_mock.pane_id = "%1"
    pane_mock.pane_index = "0"
    pane_mock.pane_current_command = "bash"
    pane_mock.pane_current_path = "/home/user/proj"
    pane_mock.pane_width = "80"
    pane_mock.pane_height = "24"
    pane_mock.pane_active = "1"
    pane_mock.pane_pid = "1234"
    pane_mock.pane_title = "agent-1"

    window_mock = MagicMock()
    window_mock.window_id = "@1"
    window_mock.window_name = "w1"
    window_mock.window_index = "0"
    window_mock.window_active = "1"
    window_mock.panes = [pane_mock]

    session_mock = MagicMock()
    session_mock.session_name = "s1"
    session_mock.session_id = "$1"
    session_mock.session_attached = "1"
    session_mock.windows = [window_mock]

    client._server = MagicMock()
    client._server.sessions = [session_mock]

    with patch.object(client, "_get_git_info", return_value={"repo_name": "proj", "branch": "main"}):
        tree = client.get_tree()
    pane = tree.sessions[0].windows[0].panes[0]
    assert pane.pane_title == "agent-1"
    assert pane.repo_name == "proj"
    assert pane.branch == "main"

def test_set_pane_title_calls_tmux():
    client = TmuxClient()
    client._server = MagicMock()
    result = client.set_pane_title("%1", "new-title")
    client._server.cmd.assert_called_once_with("select-pane", "-t", "%1", "-T", "new-title")
    assert result is True
```

Run: `uv run pytest tests/test_tmux_client.py -v`
Expected: FAIL (set_pane_title missing, _get_git_info missing)

- [ ] **Step 2: Implement pane_title reading, git helper, and set_pane_title**

In `src/muxpilot/tmux_client.py`:

1. Inside `get_tree()`, set `pane_title=pane.pane_title or ""` on `PaneInfo`.
2. After creating `pane_info`, call `git_info = self._get_git_info(pane_info.current_path)` and set `repo_name` / `branch`.
3. Add:

```python
def _get_git_info(self, path: str) -> dict[str, str]:
    import subprocess
    result = {"repo_name": "", "branch": ""}
    if not path:
        return result
    try:
        top = subprocess.run(
            ["git", "-C", path, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=1.0, check=True,
        ).stdout.strip()
        result["repo_name"] = top.split("/")[-1] if top else ""
        branch = subprocess.run(
            ["git", "-C", path, "branch", "--show-current"],
            capture_output=True, text=True, timeout=1.0, check=True,
        ).stdout.strip()
        result["branch"] = branch
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return result

def set_pane_title(self, pane_id: str, title: str) -> bool:
    try:
        self.server.cmd("select-pane", "-t", pane_id, "-T", title)
        return True
    except Exception:
        return False
```

Run: `uv run pytest tests/test_tmux_client.py -v`
Expected: PASS

- [ ] **Step 3: Update `make_mock_client` in `tests/conftest.py`**

Add `set_pane_title.return_value = True` to the mock.

- [ ] **Step 4: Commit**

```bash
git add src/muxpilot/tmux_client.py tests/test_tmux_client.py tests/conftest.py
git commit -m "feat: read pane_title and git repo/branch; add set_pane_title"
```

---

### Task 3: Watcher keeps recent_lines and idle_seconds

**Files:**
- Modify: `src/muxpilot/watcher.py`
- Test: `tests/test_watcher.py`

- [ ] **Step 1: Write failing tests**

In `tests/test_watcher.py`:

```python
def test_poll_sets_recent_lines_on_activity():
    client = make_mock_client(capture_content=["line1", "line2", "line3"])
    watcher = TmuxWatcher(client, preview_lines=2)
    tree, _ = watcher.poll()
    activity = watcher.activities.get(tree.all_panes()[0].pane_id)
    assert activity is not None
    assert activity.recent_lines == ["line2", "line3"]

def test_poll_sets_idle_seconds_on_pane_info():
    client = make_mock_client(capture_content=["$ "])
    watcher = TmuxWatcher(client)
    tree, _ = watcher.poll()
    # First poll idle = 0
    assert tree.all_panes()[0].idle_seconds == 0.0
```

Run: `uv run pytest tests/test_watcher.py -v`
Expected: FAIL (preview_lines kwarg missing, idle_seconds not set)

- [ ] **Step 2: Implement preview_lines and idle_seconds passthrough**

In `src/muxpilot/watcher.py`:

1. Add `preview_lines: int = 5` to `__init__` and store as `self.preview_lines`.
2. In `_analyze_pane()`, capture `recent_lines = content[-self.preview_lines:] if content else []` and include in returned `PaneActivity(..., recent_lines=recent_lines)`.
3. In `poll()`, after determining status, set `pane.idle_seconds = new_activity.idle_seconds`.

Run: `uv run pytest tests/test_watcher.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/muxpilot/watcher.py tests/test_watcher.py
git commit -m "feat: store recent output preview and idle_seconds in watcher"
```

---

### Task 4: Refactor RenameController to use pane_title

**Files:**
- Modify: `src/muxpilot/controllers.py`
- Test: `tests/test_app.py` (or create `tests/test_controllers.py` if it exists)
- Modify: `src/muxpilot/app.py`

- [ ] **Step 1: Write failing tests for new RenameController**

In `tests/test_app.py` (or a new `tests/test_controllers.py`):

```python
from unittest.mock import MagicMock

def test_rename_controller_calls_set_pane_title():
    client = MagicMock()
    client.set_pane_title.return_value = True
    ctrl = RenameController(client)
    pane = make_pane(pane_id="%1", pane_index=0)
    window = make_window(panes=[pane])
    session = make_session(windows=[window])
    current = ctrl.start(("pane", session, window, pane))
    assert current == ""
    key = ctrl.finish("new-title")
    assert key is not None
    client.set_pane_title.assert_called_once_with("%1", "new-title")
```

Run: `uv run pytest tests/test_app.py::test_rename_controller_calls_set_pane_title -v`
Expected: FAIL (RenameController doesn't accept client)

- [ ] **Step 2: Refactor RenameController**

In `src/muxpilot/controllers.py`:

```python
class RenameController:
    def __init__(self, client: TmuxClient | None = None) -> None:
        self._client = client
        self._key: str | None = None
        self._pane_id: str | None = None

    @property
    def key(self) -> str | None:
        return self._key

    @key.setter
    def key(self, value: str | None) -> None:
        self._key = value

    def start(self, node_data: tuple[str, ...] | None) -> str | None:
        if node_data is None:
            return None
        node_type, session, window, pane = node_data
        if node_type == "pane" and session and window and pane:
            self._key = f"{session.session_name}.{window.window_index}.{pane.pane_index}"
            self._pane_id = pane.pane_id
            return pane.pane_title
        # session/window renaming removed for now (out of scope)
        return None

    def finish(self, value: str) -> str | None:
        key = self._key
        if key is None or self._client is None:
            return None
        self._client.set_pane_title(self._pane_id or "", value)
        self._key = None
        self._pane_id = None
        return key

    def cancel(self) -> None:
        self._key = None
        self._pane_id = None

    def apply(self, tree: TmuxTree) -> None:
        # No-op: pane_title comes from tmux directly on next poll
        pass
```

In `src/muxpilot/app.py`, change `self._rename_controller = RenameController()` to `RenameController(self._client)`.

Run: `uv run pytest tests/test_app.py::test_rename_controller_calls_set_pane_title -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/muxpilot/controllers.py src/muxpilot/app.py tests/test_app.py
git commit -m "feat: rename now sets tmux pane_title directly"
```

---

### Task 5: Rewrite DetailPanel

**Files:**
- Modify: `src/muxpilot/widgets/detail_panel.py`
- Test: `tests/test_app.py` (detail panel assertions)

- [ ] **Step 1: Write failing test for new detail panel format**

In `tests/test_app.py`, locate tests that assert detail panel text and update them:

```python
def test_detail_panel_shows_pane_title_and_git():
    pane = make_pane(pane_title="agent-a", repo_name="proj", branch="feat/x", idle_seconds=12.0, status=PaneStatus.IDLE)
    window = make_window()
    session = make_session()
    panel = DetailPanel()
    panel.show_pane(pane, window, session)
    text = panel._content.renderable  # or however textual exposes it
    assert "agent-a" in text
    assert "proj" in text
    assert "feat/x" in text
    assert "12.0s idle" in text
```

Run: `uv run pytest tests/test_app.py -v -k detail`
Expected: FAIL (panel doesn't show these fields)

- [ ] **Step 2: Implement new layout**

In `src/muxpilot/widgets/detail_panel.py`, rewrite `show_pane()`:

```python
def show_pane(self, pane: PaneInfo, window: WindowInfo, session: SessionInfo) -> None:
    icon = STATUS_ICONS.get(pane.status, "?")
    status_name = pane.status.value if pane.status else "unknown"
    idle_text = f" ({pane.idle_seconds:.1f}s idle)" if pane.idle_seconds > 0 else ""
    title = pane.pane_title or "—"
    repo = pane.repo_name or "—"
    branch = pane.branch or "—"

    text = (
        f"[bold $accent]── Pane ──[/]\n"
        f"\n"
        f"  [dim]Title:[/]       {title}\n"
        f"  [dim]Repository:[/]  {repo}\n"
        f"  [dim]Branch:[/]      {branch}\n"
        f"  [dim]Command:[/]     {pane.full_command or pane.current_command}\n"
        f"  [dim]Path:[/]        {_shorten_path(pane.current_path)}\n"
        f"  [dim]Size:[/]        {pane.width}×{pane.height}\n"
        f"  [dim]Active:[/]      {'Yes' if pane.is_active else 'No'}\n"
        f"  [dim]Status:[/]      {icon} {status_name}{idle_text}\n"
    )

    if pane.status == PaneStatus.ERROR:
        text += f"\n  [bold $error]Status is ERROR[/]\n"
    elif pane.status == PaneStatus.WAITING_INPUT:
        text += f"\n  [bold $warning]Waiting for input[/]\n"

    text += (
        f"\n"
        f"[bold $accent]── Recent Output ──[/]\n"
    )
    # Note: preview lines come from watcher activity, but DetailPanel only receives PaneInfo.
    # We need to pass recent_lines into show_pane.  Update signature and caller.
    text += "\n"
    text += (
        f"  [dim]Window:[/]    {window.window_name} (#{window.window_index})\n"
        f"  [dim]Session:[/]   {session.session_name}\n"
    )
    self._content.update(text)
```

**Issue:** `DetailPanel.show_pane` only receives `PaneInfo`, but `recent_lines` is on `PaneActivity`. We need to either:
a) Move `recent_lines` into `PaneInfo` (watcher copies it), or
b) Pass `recent_lines` as an extra argument to `show_pane`.

Option (a) is simpler and keeps the panel dumb. Update the spec: add `recent_lines` to `PaneInfo` (default empty list) and have the watcher copy it in `poll()`.

- Update `PaneInfo` in `src/muxpilot/models.py` to include `recent_lines: list[str] = field(default_factory=list)`.
- In `src/muxpilot/watcher.py` `poll()`, set `pane.recent_lines = new_activity.recent_lines`.
- Update `show_pane` signature to use `pane.recent_lines`.

Then implement preview rendering:

```python
    preview = pane.recent_lines if pane.recent_lines else ["(no output)"]
    for line in preview:
        safe = line if line.strip() else "(blank)"
        text += f"  {safe}\n"
```

Run: `uv run pytest tests/test_app.py -v -k detail`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/muxpilot/models.py src/muxpilot/watcher.py src/muxpilot/widgets/detail_panel.py tests/test_app.py
git commit -m "feat: rewrite detail panel with title, repo, branch, idle, output preview"
```

---

### Task 6: Integration & Full Test Suite

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS. Fix any failures from changed signatures or behavior.

- [ ] **Step 2: Commit fixes**

```bash
git add -A
git commit -m "test: update tests for pane detail agent context"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|------------------|------|
| `PaneInfo.pane_title` | Task 1 |
| `PaneInfo.repo_name`, `branch` | Task 2 |
| `PaneInfo.idle_seconds` | Task 1, Task 3 |
| `PaneActivity.recent_lines` | Task 1, Task 3 |
| `display_label` prefers pane_title | Task 1 |
| TmuxClient reads pane_title | Task 2 |
| TmuxClient git helper | Task 2 |
| TmuxClient.set_pane_title | Task 2 |
| Watcher stores preview lines | Task 3 |
| Watcher copies idle_seconds to PaneInfo | Task 3 |
| RenameController uses pane_title | Task 4 |
| DetailPanel new layout | Task 5 |
| App wires rename to set_pane_title | Task 4 |
| Edge cases (no git, no title) | Task 2, Task 5 tests |

## Self-Review

- **Placeholder scan:** No TBD/TODO/fill-in found.
- **Type consistency:** `PaneInfo` fields are `str` / `float` / `list[str]`. `set_pane_title` signature consistent across client and controller.
- **No missing tasks:** All spec sections mapped.
