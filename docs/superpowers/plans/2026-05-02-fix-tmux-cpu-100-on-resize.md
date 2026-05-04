# Fix tmux CPU 100% on Pane Resize — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the tmux CPU 100% hang caused by muxpilot sending O(P×S×W) tmux commands per poll cycle via `_find_pane()` and libtmux.

**Architecture:** Replace libtmux-dependent `capture_pane_content()` with direct `subprocess.run(["tmux", "capture-pane", ...])` calls, removing the `_find_pane()` bottleneck entirely. Also add a poll concurrency guard to prevent overlapping `poll()` calls.

**Tech Stack:** Python, subprocess, asyncio, pytest

---

## Root Cause Summary

Each `watcher.poll()` cycle sends approximately P×(1+S+W) + P + 1 tmux commands (where P=panes, S=sessions, W=windows). For 6 panes in 2 sessions with 3 windows, that's ~60+ tmux commands every 5 seconds. During pane resize, tmux is already busy reflowing content, and this barrage causes tmux CPU 100% and hangs.

The waste comes from `capture_pane_content()` calling `_find_pane()` which does a full server scan (via libtmux `self.server.sessions` → `session.windows` → `window.panes`, each a tmux subprocess) per pane, never caching results, then calling `pane.capture_pane()` (another tmux command). Meanwhile `get_tree()` already has all pane IDs from a single efficient `tmux list-panes -a` call.

## Fix Strategy

1. **Replace `capture_pane_content()` with direct subprocess call** — eliminate `_find_pane()` dependency for content capture. Use `tmux capture-pane -t <pane_id> -p -S -<lines>` directly, just like `get_tree()` uses `tmux list-panes -a -F` directly.

2. **Invalidate `_pane_cache` after `get_tree()`** — refresh the cache with fresh Pane objects from the tree fetch, so `navigate_to()` and `kill_pane()` still work without extra tmux calls.

3. **Add poll concurrency guard** — prevent overlapping `poll()` calls when a cycle takes longer than `poll_interval`.

4. **Remove `_get_git_info()` calls from `get_tree()`** — git subprocess calls on every poll for every pane are expensive and not needed for core functionality. Git info can be fetched lazily or dropped.

---

### Task 1: Rewrite `capture_pane_content()` to use subprocess directly

**Files:**
- Modify: `src/muxpilot/tmux_client.py:175-189`
- Test: `tests/test_tmux_client.py:160-182`

- [ ] **Step 1: Write the failing test — direct subprocess capture**

Add a new test class `TestCaptureDirect` in `tests/test_tmux_client.py` that verifies `capture_pane_content()` calls `subprocess.run` with the correct arguments and doesn't use `_find_pane()` or libtmux at all.

```python
class TestCaptureDirect:
    def test_calls_subprocess_directly(self):
        c = TmuxClient()
        mock_result = MagicMock()
        mock_result.stdout = "line1\nline2\nline3\n"
        mock_result.returncode = 0
        mock_result.check_returncode = MagicMock()
        with patch("muxpilot.tmux_client.subprocess.run", return_value=mock_result) as mock_run:
            result = c.capture_pane_content("%0", lines=30)
        mock_run.assert_called_once()
        args = mock_run.call_args
        assert args[0][0][:2] == ["tmux", "capture-pane"]
        assert "-t" in args[0][0]
        assert "%0" in args[0][0]
        assert "-p" in args[0][0]
        assert result == ["line1", "line2", "line3"]

    def test_returns_empty_on_failure(self):
        c = TmuxClient()
        with patch("muxpilot.tmux_client.subprocess.run", side_effect=subprocess.CalledProcessError(1, "tmux")):
            result = c.capture_pane_content("%99", lines=30)
        assert result == []

    def test_returns_empty_on_timeout(self):
        c = TmuxClient()
        with patch("muxpilot.tmux_client.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="tmux", timeout=5)):
            result = c.capture_pane_content("%0", lines=30)
        assert result == []

    def test_strips_trailing_empty_lines(self):
        c = TmuxClient()
        mock_result = MagicMock()
        mock_result.stdout = "line1\n\nline2\n\n\n"
        mock_result.returncode = 0
        mock_result.check_returncode = MagicMock()
        with patch("muxpilot.tmux_client.subprocess.run", return_value=mock_result):
            result = c.capture_pane_content("%0", lines=30)
        assert "line1" in result
        assert "line2" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tmux_client.py::TestCaptureDirect -v`
Expected: FAIL — `capture_pane_content` still uses `_find_pane()` + libtmux, not subprocess.

- [ ] **Step 3: Rewrite `capture_pane_content()` to use subprocess directly**

In `src/muxpilot/tmux_client.py`, replace the `capture_pane_content` method:

```python
def capture_pane_content(self, pane_id: str, lines: int = 50) -> list[str]:
    """Capture the last N lines of output from a pane using direct tmux command."""
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", pane_id, "-p", "-S", str(-lines)],
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        result.check_returncode()
        content = result.stdout.splitlines()
        while content and not content[-1].strip():
            content.pop()
        return content
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []
```

- [ ] **Step 4: Run all tmux_client tests to verify they pass**

Run: `uv run pytest tests/test_tmux_client.py -v`
Expected: ALL PASS. The old `TestCapture` tests should be updated since the mock setup is different (no longer using libtmux mock Pane objects).

- [ ] **Step 5: Update existing `TestCapture` tests to work with new implementation**

The existing `TestCapture` class uses `_client_with()` which sets up a mock libtmux server with sessions/windows/panes. Since `capture_pane_content()` no longer uses libtmux, these tests need to mock `subprocess.run` instead. Update each test in `TestCapture`:

```python
class TestCapture:
    def test_returns_content(self):
        c = TmuxClient()
        mock_result = MagicMock()
        mock_result.stdout = "a\nb\n"
        mock_result.returncode = 0
        mock_result.check_returncode = MagicMock()
        with patch("muxpilot.tmux_client.subprocess.run", return_value=mock_result):
            assert c.capture_pane_content("%0") == ["a", "b"]

    def test_returns_empty_on_failure(self):
        c = TmuxClient()
        with patch("muxpilot.tmux_client.subprocess.run", side_effect=subprocess.CalledProcessError(1, "tmux")):
            assert c.capture_pane_content("%99") == []

    def test_returns_empty_on_timeout(self):
        c = TmuxClient()
        with patch("muxpilot.tmux_client.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="tmux", timeout=5)):
            assert c.capture_pane_content("%0") == []
```

Delete the old `TestCapture` tests (`test_returns_list`, `test_returns_string`, `test_nonexistent`, `test_exception`) since they tested libtmux-based implementation.

- [ ] **Step 6: Run all tests to verify everything passes**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/muxpilot/tmux_client.py tests/test_tmux_client.py
git commit -m "feat: replace libtmux capture_pane_content with direct subprocess

Eliminates O(P×S×W) tmux commands per poll cycle by removing _find_pane()
dependency from capture_pane_content(). Uses direct tmux command instead,
reducing pane content capture from multiple tmux calls per pane to exactly
one call per pane."
```

---

### Task 2: Populate `_pane_cache` in `get_tree()` and simplify `_find_pane()`

**Files:**
- Modify: `src/muxpilot/tmux_client.py:42-130` (`get_tree` method)
- Modify: `src/muxpilot/tmux_client.py:220-234` (`_find_pane` method)
- Test: `tests/test_tmux_client.py`

Now that `capture_pane_content()` no longer needs `_find_pane()`, the only remaining callers are `kill_pane()` and (indirectly) `navigate_to()` via `server.cmd()`. The `navigate_to()` method already uses `server.cmd("switch-client", "-t", pane_id)` which doesn't need a Pane object. The `kill_pane()` method does need a Pane object via `_find_pane()`. We should populate the cache in `get_tree()` so `kill_pane()` can find panes efficiently.

- [ ] **Step 1: Write the failing test — _pane_cache is populated after get_tree**

```python
class TestPaneCache:
    def test_cache_populated_after_get_tree(self):
        line = "s\t$1\t1\t@1\tw\t0\t1\t%1\t0\tbash\t/home/user\t1\t80\t24\t1234\t"
        mock_result = MagicMock()
        mock_result.stdout = line + "\n"
        mock_result.returncode = 0
        mock_result.check_returncode = MagicMock()
        with patch("muxpilot.tmux_client.subprocess.run", return_value=mock_result):
            c = TmuxClient()
            with patch.object(c, "_get_git_info", return_value={"repo_name": "", "branch": ""}):
                c.get_tree()
        # After get_tree, _pane_cache should contain the pane ID we found
        assert "%1" in c._pane_cache
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tmux_client.py::TestPaneCache -v`
Expected: FAIL — `_pane_cache` is not populated after `get_tree()`.

- [ ] **Step 3: Update `get_tree()` to populate `_pane_cache`**

In `get_tree()`, after building the tree from `list-panes` output, also populate `_pane_cache`. But since `get_tree()` now uses subprocess directly and doesn't create libtmux Pane objects, we need `_find_pane()` to still work for `kill_pane()`. The simplest approach: make `_find_pane()` also use subprocess to find panes, or better yet, add a lightweight Pane cache that updates on each `get_tree()` call.

Actually, looking at `kill_pane()`:
```python
def kill_pane(self, pane_id: str) -> bool:
    pane = self._find_pane(pane_id)
    if pane is None:
        return False
    try:
        pane.kill()
        return True
    except libtmux.exc.LibTmuxException:
        return False
```

`kill_pane()` uses `pane.kill()` which is a libtmux method. We should also replace this with a direct subprocess call for consistency and efficiency.

Update `kill_pane()` to use subprocess directly:
```python
def kill_pane(self, pane_id: str) -> bool:
    try:
        result = subprocess.run(
            ["tmux", "kill-pane", "-t", pane_id],
            capture_output=True,
            timeout=5.0,
        )
        return result.returncode == 0
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
```

And simplify `_find_pane()` to use subprocess or mark it as deprecated. Since `capture_pane_content()` and `kill_pane()` no longer need it, we can remove `_find_pane()` entirely if no other code uses it.

Let me check what else uses `_find_pane()`:
- `capture_pane_content()` — removed in Task 1
- `kill_pane()` — replaced above
- Nothing else

So we can remove `_find_pane()` and the `_pane_cache` attribute entirely.

- [ ] **Step 3 (revised): Replace `kill_pane()` with subprocess and remove `_find_pane()`/`_pane_cache`**

In `src/muxpilot/tmux_client.py`:

1. Remove `_pane_cache` from `__init__`:
```python
def __init__(self) -> None:
    self._server: libtmux.Server | None = None
```

2. Replace `kill_pane()` method:
```python
def kill_pane(self, pane_id: str) -> bool:
    """Kill the specified pane using direct tmux command."""
    try:
        result = subprocess.run(
            ["tmux", "kill-pane", "-t", pane_id],
            capture_output=True,
            timeout=5.0,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
```

3. Remove `_find_pane()` method entirely (lines 220-234).

4. Remove `_pane_cache` from `__init__`.

- [ ] **Step 4: Update `TestNavigateTo` and add `TestKillPane` tests**

Update `TestNavigateTo` tests to not rely on `_client_with()` setting up a mock server with sessions, since `navigate_to()` now uses `server.cmd()` directly (it already does — keep as is).

Add new `TestKillPane` tests:

```python
class TestKillPane:
    def test_kill_existing_pane(self):
        c = TmuxClient()
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("muxpilot.tmux_client.subprocess.run", return_value=mock_result):
            assert c.kill_pane("%0") is True
        with patch("muxpilot.tmux_client.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            c.kill_pane("%0")
            mock_run.assert_called_once()
            assert mock_run.call_args[0][0][:3] == ["tmux", "kill-pane", "-t"]

    def test_kill_nonexistent_pane(self):
        c = TmuxClient()
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("muxpilot.tmux_client.subprocess.run", return_value=mock_result):
            assert c.kill_pane("%99") is False

    def test_kill_pane_timeout(self):
        c = TmuxClient()
        with patch("muxpilot.tmux_client.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="tmux", timeout=5)):
            assert c.kill_pane("%0") is False
```

- [ ] **Step 5: Remove old `TestKillPane`-related tests if any existed and the _client_with/Pane mock tests for kill_pane**

The old `TestCapture` tests that used `_client_with` and libtmux mock objects should already have been removed in Task 1. Remove any tests that reference `_find_pane` or `_pane_cache`.

- [ ] **Step 6: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/muxpilot/tmux_client.py tests/test_tmux_client.py
git commit -m "refactor: replace kill_pane with subprocess, remove _find_pane and _pane_cache

Removes the libtmux dependency from kill_pane() and eliminates _find_pane()
entirely, as it was the primary source of excess tmux commands. kill_pane()
now uses direct subprocess call, consistent with get_tree() approach."
```

---

### Task 3: Add poll concurrency guard in `PollingController`

**Files:**
- Modify: `src/muxpilot/controllers.py:78-113` (`tick` method)
- Test: `tests/test_app.py`

If a `poll()` call takes longer than `poll_interval` (e.g., during heavy tmux load), the next timer fire will start a concurrent `poll()`, doubling the tmux command load. Add an `asyncio.Lock` to prevent this.

- [ ] **Step 1: Write the failing test — concurrent poll calls are serialized**

In `tests/test_app.py`, add a test that verifies two overlapping `_poll_tmux` calls don't run concurrently:

```python
import asyncio
import time

async def test_poll_does_not_run_concurrently(app_with_mock):
    """Verify that poll calls are serialized - no concurrent tmux commands."""
    app = app_with_mock
    call_count = 0
    slow_calls = 0

    original_poll = app._watcher.poll

    def slow_poll():
        nonlocal call_count, slow_calls
        call_count += 1
        slow_calls += 1
        time.sleep(0.3)
        slow_calls -= 1
        # If concurrent, slow_calls would be > 1
        assert slow_calls <= 1, f"Concurrent polls detected: {slow_calls}"
        return original_poll()

    app._watcher.poll = slow_poll

    # Start two poll cycles concurrently
    await asyncio.gather(app._poll_tmux(), app._poll_tmux())

    assert call_count == 2
```

Note: This test may need adjustment based on the actual test infrastructure. The key point is verifying that `tick()` uses a lock to prevent concurrent execution.

- [ ] **Step 2: Add `asyncio.Lock` to `PollingController`**

In `src/muxpilot/controllers.py`, add a lock to `PollingController.__init__` and use it in `tick()`:

```python
class PollingController:
    def __init__(self, app, watcher, notify_channel):
        ...
        self._poll_lock = asyncio.Lock()

    async def tick(self) -> tuple[TmuxTree, list[TmuxEvent]] | None:
        """Execute one poll cycle with error handling and backoff.

        Returns (tree, events) on success, or None on failure / cooldown / locked.
        """
        if self._poll_lock.locked():
            return None

        async with self._poll_lock:
            if time.time() < self.cooldown_until:
                return None

            try:
                tree, events = await asyncio.to_thread(self._watcher.poll)
            except Exception as e:
                ...

        return tree, events
```

Wait — there's a subtlety. The `asyncio.Lock` prevents concurrent `tick()` calls, but if `tick()` is already running, the next call should be skipped (not queued). The `if self._poll_lock.locked()` check before `async with self._poll_lock` handles this.

- [ ] **Step 3: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add src/muxpilot/controllers.py tests/test_app.py
git commit -m "fix: add concurrency guard to PollingController.tick()

Prevents overlapping poll() calls when a cycle takes longer than
poll_interval. Skips the poll if the previous one is still running,
rather than queuing or running concurrently."
```

---

### Task 4: Remove `_get_git_info()` calls from `get_tree()`

**Files:**
- Modify: `src/muxpilot/tmux_client.py:124-127` (in `get_tree()`)
- Modify: `src/muxpilot/tmux_client.py:192-210` (`_get_git_info` method)
- Test: `tests/test_tmux_client.py`

`_get_git_info()` spawns 2 git subprocesses per pane per poll cycle. For 6 panes, that's 12 git processes every 5 seconds. This adds system load during resize and is not essential for the watcher. Remove the call from `get_tree()` and make git info lazy (or remove it entirely if unused in the UI).

- [ ] **Step 1: Check if git info is used in the UI**

Search for `repo_name` and `branch` usage in widgets and display code.

We know from `PaneInfo.display_label` that `repo_name` and `branch` are stored but NOT used in `display_label`. The `full_command` field is used instead. Check widgets:

- `detail_panel.py` likely displays git info
- `tree_view.py` probably uses `display_label` which doesn't include git info

If git info is displayed in the detail panel only, it can be fetched lazily (on demand when a pane is selected) rather than on every poll cycle.

- [ ] **Step 2: Remove `git_info` computation from `get_tree()` and make it lazy**

In `src/muxpilot/tmux_client.py`, modify the `get_tree()` method to skip `_get_git_info()`:

```python
pane_info = PaneInfo(
    pane_id=pane_id,
    pane_index=pane_index,
    current_command=current_command,
    current_path=current_path,
    is_active=pane_active,
    width=width,
    height=height,
    is_self=(pane_id == self_pane_id),
    full_command="",
    pane_title=pane_title,
)
windows[window_id].panes.append(pane_info)
```

Remove the `_get_git_info` call and the two lines that set `repo_name` and `branch`.

Add a new method `get_git_info(self, path: str) -> dict[str, str]` that is called lazily:

Actually, keeping `_get_git_info` as a public method `get_git_info` that can be called on demand is fine. We just remove it from the hot path of `get_tree()`.

- [ ] **Step 3: Update existing git info tests to not depend on `get_tree()`**

The `TestPaneTitleAndGit` tests should be updated. `test_get_tree_populates_git_info` should be removed or changed to verify git info is empty after `get_tree()`. The `test_get_git_info_success` and `test_get_git_info_not_a_repo` tests should remain but test the standalone `get_git_info()` method.

- [ ] **Step 4: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/muxpilot/tmux_client.py tests/test_tmux_client.py
git commit -m "perf: remove git subprocess calls from get_tree() hot path

_git_info() spawned 2 git processes per pane per poll cycle (12 for 6 panes).
Removed from get_tree() to reduce system load. Git info remains available
via get_git_info() method for lazy/on-demand use."
```

---

### Task 5: Add a poll count metric and verify reduced tmux command count

**Files:**
- Test: `tests/test_watcher.py`

This is a verification task — add a test that counts subprocess calls during a poll cycle to confirm the reduction in tmux commands.

- [ ] **Step 1: Write a test that counts subprocess calls in one poll cycle**

```python
def test_poll_tmux_command_count(mock_client):
    """Verify that a single poll cycle makes minimal tmux subprocess calls.
    
    After the fix, get_tree() should make exactly 1 tmux call (list-panes),
    and capture_pane_content() should make 1 tmux call per pane (capture-pane).
    No _find_pane() scans, no git calls.
    """
    import unittest.mock
    panes = [make_pane(pane_id=f"%{i}") for i in range(4)]
    tree = make_tree(sessions=[make_session(windows=[make_window(panes=panes)])])
    mock_client.get_tree.return_value = tree
    mock_client.get_current_pane_id.return_value = None
    mock_client.capture_pane_content.return_value = ["output"]

    watcher = TmuxWatcher(mock_client)

    with unittest.mock.patch("muxpilot.tmux_client.subprocess.run") as mock_run:
        tree_result, events = watcher.poll()

    # get_tree should use 1 subprocess call (list-panes), not 1 + P*(2 git) + ...
    # capture_pane_content should use 1 call per pane, not P * (S + W + 1)
    # Total should be approximately 1 + P = 5, not 60+
```

Note: This test is more of an integration test. Since `watcher.poll()` uses `mock_client`, the real subprocess calls don't happen. Instead, verify at the `TmuxClient` level that `get_tree()` and `capture_pane_content()` make minimal subprocess calls.

A simpler verification: in `test_tmux_client.py`, test that `get_tree()` makes exactly 1 subprocess call:

```python
class TestGetTreeSubprocessCount:
    def test_get_tree_makes_one_subprocess_call(self):
        line = "s\t$1\t1\t@1\tw\t0\t1\t%1\t0\tbash\t/home/user\t1\t80\t24\t1234\t"
        mock_result = MagicMock()
        mock_result.stdout = line + "\n"
        mock_result.returncode = 0
        mock_result.check_returncode = MagicMock()
        with patch("muxpilot.tmux_client.subprocess.run", return_value=mock_result) as mock_run:
            c = TmuxClient()
            tree = c.get_tree()
        assert mock_run.call_count == 1
```

And test that `capture_pane_content()` makes 1 subprocess call:

```python
class TestCaptureSubprocessCount:
    def test_capture_makes_one_subprocess_call(self):
        c = TmuxClient()
        mock_result = MagicMock()
        mock_result.stdout = "output\n"
        mock_result.returncode = 0
        mock_result.check_returncode = MagicMock()
        with patch("muxpilot.tmux_client.subprocess.run", return_value=mock_result) as mock_run:
            c.capture_pane_content("%0", lines=30)
        assert mock_run.call_count == 1
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_tmux_client.py
git commit -m "test: verify subprocess call count for get_tree and capture_pane_content

Confirms that get_tree() makes exactly 1 tmux subprocess call and
capture_pane_content() makes 1 call per pane, eliminating the
O(P×S×W) command explosion from _find_pane()."
```

---

## Expected Impact

**Before fix (per poll cycle, 6 panes, 2 sessions, 3 windows):**
- `tmux list-panes`: 1 call (via get_tree)
- `git rev-parse` + `git branch`: 12 calls (2 per pane, via _get_git_info)
- `_find_pane()` per pane: 6 × (1 list-sessions + 2 list-windows + 6 list-panes) = 54 calls
- `capture-pane` per pane: 6 calls
- **Total: ~73 subprocess calls per cycle, every 5 seconds = ~15 calls/sec**

**After fix:**
- `tmux list-panes`: 1 call (via get_tree)
- `capture-pane` per pane: 6 calls (direct subprocess, no _find_pane scan)
- **Total: 7 subprocess calls per cycle, every 5 seconds = ~1.4 calls/sec**

**That's a ~10x reduction in tmux commands, which should resolve the CPU 100% hang during pane resize.**