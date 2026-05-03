# Toast Notification → WAITING Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow external processes to set a tmux pane's status to `WAITING_INPUT` by sending a FIFO message containing the pane id and a configurable regex pattern.

**Architecture:** Extend `TmuxWatcher` with a `process_notification()` method that parses notification messages for pane ids and a regex match. Integrate it into `MuxpilotApp._check_notifications()` so matching messages update the pane status and refresh the UI immediately, while non-matching messages continue to display as toasts.

**Tech Stack:** Python 3.11+, Textual, pytest, unittest.mock, tomllib

---

## File Map

| File | Responsibility |
|------|---------------|
| `src/muxpilot/watcher.py` | Core change: add `waiting_trigger_pattern` config loading and `process_notification()` method |
| `src/muxpilot/app.py` | Integrate notification processing into `_check_notifications()`; refresh UI on status change events |
| `config.example.toml` | Document the new `waiting_trigger_pattern` setting |
| `tests/test_watcher.py` | Unit tests for `process_notification()` behavior |
| `tests/test_watcher_config.py` | Config loading tests for `waiting_trigger_pattern` |
| `tests/test_app.py` | Integration tests for `_check_notifications()` triggering UI refresh |

---

## Task 1: Load `waiting_trigger_pattern` from config in TmuxWatcher

**Files:**
- Modify: `src/muxpilot/watcher.py:68-96`
- Test: `tests/test_watcher_config.py`

- [ ] **Step 1: Write the failing test**

```python
def test_watcher_reads_waiting_trigger_pattern_from_config():
    import tempfile, pathlib, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write('[notifications]\nwaiting_trigger_pattern = "WAITING"\n')
        path = f.name
    client = make_mock_client()
    try:
        watcher = TmuxWatcher(client, config_path=pathlib.Path(path))
        assert watcher.waiting_trigger_pattern is not None
        assert watcher.waiting_trigger_pattern.pattern == "WAITING"
    finally:
        os.unlink(path)


def test_watcher_waiting_trigger_pattern_defaults_to_none():
    client = make_mock_client()
    watcher = TmuxWatcher(client, config_path=pathlib.Path("/nonexistent-config"))
    assert watcher.waiting_trigger_pattern is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_watcher_config.py::test_watcher_reads_waiting_trigger_pattern_from_config tests/test_watcher_config.py::test_watcher_waiting_trigger_pattern_defaults_to_none -v`

Expected: FAIL with `AttributeError: 'TmuxWatcher' object has no attribute 'waiting_trigger_pattern'`

- [ ] **Step 3: Write minimal implementation**

In `src/muxpilot/watcher.py`, inside `TmuxWatcher.__init__`, add after the existing pattern initializations (around line 69):

```python
        self.waiting_trigger_pattern: re.Pattern[str] | None = None
```

Then in the config loading block (around line 92, after the `notify_cfg` block), add:

```python
                    waiting_pattern = notify_cfg.get("waiting_trigger_pattern", "")
                    if waiting_pattern:
                        self.waiting_trigger_pattern = re.compile(waiting_pattern)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_watcher_config.py::test_watcher_reads_waiting_trigger_pattern_from_config tests/test_watcher_config.py::test_watcher_waiting_trigger_pattern_defaults_to_none -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_watcher_config.py src/muxpilot/watcher.py
git commit -m "feat: load waiting_trigger_pattern from config"
```

---

## Task 2: Implement `TmuxWatcher.process_notification()`

**Files:**
- Modify: `src/muxpilot/watcher.py`
- Test: `tests/test_watcher.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_watcher.py` inside a new `TestProcessNotification` class:

```python
class TestProcessNotification:
    """Tests for process_notification — toast-triggered status changes."""

    def _watcher_with_pattern(self, pattern="WAITING"):
        tree = make_tree(sessions=[
            make_session(windows=[make_window(panes=[
                make_pane(pane_id="%0", status=PaneStatus.ACTIVE),
                make_pane(pane_id="%1", status=PaneStatus.ERROR),
            ])])
        ])
        client = make_mock_client(tree=tree)
        watcher = TmuxWatcher(client, config_path=pathlib.Path("/nonexistent"))
        watcher.waiting_trigger_pattern = re.compile(pattern)
        # Seed activities so panes are known
        watcher.poll()
        return watcher

    def test_matching_message_returns_event_and_updates_status(self):
        w = self._watcher_with_pattern()
        event = w.process_notification("Task complete %0 WAITING")
        assert event is not None
        assert event.event_type == "status_changed"
        assert event.pane_id == "%0"
        assert event.new_status == PaneStatus.WAITING_INPUT
        assert w.activities["%0"].status == PaneStatus.WAITING_INPUT

    def test_matching_message_without_pane_id_returns_none(self):
        w = self._watcher_with_pattern()
        event = w.process_notification("Just WAITING here")
        assert event is None

    def test_message_with_pane_id_but_no_pattern_match_returns_none(self):
        w = self._watcher_with_pattern()
        event = w.process_notification("%0 is done")
        assert event is None

    def test_unknown_pane_returns_none(self):
        w = self._watcher_with_pattern()
        event = w.process_notification("%99 WAITING")
        assert event is None

    def test_disabled_pattern_returns_none(self):
        w = self._watcher_with_pattern()
        w.waiting_trigger_pattern = None
        event = w.process_notification("%0 WAITING")
        assert event is None

    def test_regex_pattern_match(self):
        w = self._watcher_with_pattern(pattern="(?i)waiting|ready")
        event = w.process_notification("%0 ready for input")
        assert event is not None
        assert event.new_status == PaneStatus.WAITING_INPUT

    def test_already_waiting_returns_event(self):
        """Even if pane is already WAITING_INPUT, return event for UI feedback."""
        w = self._watcher_with_pattern()
        w.activities["%0"].status = PaneStatus.WAITING_INPUT
        event = w.process_notification("%0 WAITING")
        assert event is not None
        assert event.new_status == PaneStatus.WAITING_INPUT

    def test_error_to_waiting_transition(self):
        w = self._watcher_with_pattern()
        event = w.process_notification("%1 WAITING")
        assert event is not None
        assert event.old_status == PaneStatus.ERROR
        assert event.new_status == PaneStatus.WAITING_INPUT
        assert w.activities["%1"].status == PaneStatus.WAITING_INPUT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_watcher.py::TestProcessNotification -v`

Expected: FAIL with `AttributeError: 'TmuxWatcher' object has no attribute 'process_notification'`

- [ ] **Step 3: Write minimal implementation**

Add `import re` is already at the top of `watcher.py`. Add the following method to `TmuxWatcher` (after `_detect_structural_changes`, around line 306):

```python
    def process_notification(self, message: str) -> TmuxEvent | None:
        """Parse a notification message and update pane status if it matches.

        Returns a TmuxEvent on status change, or None if no match.
        """
        if self.waiting_trigger_pattern is None:
            return None

        # Find first pane id token
        pane_match = re.search(r"%[0-9]+", message)
        if not pane_match:
            return None
        pane_id = pane_match.group(0)

        # Check pattern match
        if not self.waiting_trigger_pattern.search(message):
            return None

        activity = self.activities.get(pane_id)
        if activity is None:
            return None

        old_status = activity.status
        activity.status = PaneStatus.WAITING_INPUT

        return TmuxEvent(
            event_type="status_changed",
            pane_id=pane_id,
            old_status=old_status,
            new_status=PaneStatus.WAITING_INPUT,
            message=f"{pane_id}: {old_status.value} → waiting",
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_watcher.py::TestProcessNotification -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_watcher.py src/muxpilot/watcher.py
git commit -m "feat: implement process_notification in TmuxWatcher"
```

---

## Task 3: Integrate notification processing into App

**Files:**
- Modify: `src/muxpilot/app.py:450-456`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_app.py` in the "Notifications" section:

```python
@pytest.mark.asyncio
async def test_notification_waiting_trigger_updates_ui():
    """A FIFO message matching waiting_trigger_pattern should refresh the tree."""
    from muxpilot.models import TmuxEvent, PaneStatus

    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[
            make_pane(pane_id="%0", status=PaneStatus.ACTIVE),
        ])])
    ])
    app = _patched_app(tree=tree)
    # Seed the watcher with an activity
    app._watcher.poll()
    app._watcher.waiting_trigger_pattern = re.compile("WAITING")

    async with app.run_test() as pilot:
        tw = app.query_one("#tmux-tree", TmuxTreeView)
        app._notify_channel.receive = MagicMock(side_effect=["%0 WAITING", None])
        app._notify_channel.send.reset_mock()

        await app._check_notifications()
        await pilot.pause()

        # The tree should have refreshed with WAITING status
        assert app._watcher.activities["%0"].status == PaneStatus.WAITING_INPUT
        # A confirmation toast should have been shown
        notify_calls = [call.args for call in app.notify.call_args_list]
        assert any("%0" in str(args) and "waiting" in str(args).lower() for args in notify_calls)


@pytest.mark.asyncio
async def test_notification_no_match_shows_raw_toast():
    """A FIFO message that does not match should display as a normal toast."""
    tree = make_tree(sessions=[
        make_session(windows=[make_window(panes=[make_pane(pane_id="%0")])])
    ])
    app = _patched_app(tree=tree)
    app._watcher.waiting_trigger_pattern = re.compile("WAITING")

    async with app.run_test() as pilot:
        app._notify_channel.receive = MagicMock(side_effect=["hello world", None])
        app._notify_channel.send.reset_mock()

        await app._check_notifications()
        await pilot.pause()

        app.notify.assert_called_once_with("hello world", timeout=5)
```

Note: `app.notify` may need to be mocked. In `_patched_app`, add `app.notify = MagicMock()` if it is not already a mock.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_app.py::test_notification_waiting_trigger_updates_ui tests/test_app.py::test_notification_no_match_shows_raw_toast -v`

Expected: FAIL because `_check_notifications` does not call `process_notification`

- [ ] **Step 3: Write minimal implementation**

Modify `src/muxpilot/app.py` in `_check_notifications` (around line 450):

```python
    async def _check_notifications(self) -> None:
        """Consume messages from NotifyChannel and display as Textual notifications."""
        while True:
            msg = self._notify_channel.receive()
            if msg is None:
                break
            event = self._watcher.process_notification(msg)
            if event:
                # Refresh UI to reflect the status change
                if self._watcher._last_tree is not None:
                    self._apply_labels(self._watcher._last_tree)
                    tree_widget = self.query_one("#tmux-tree", TmuxTreeView)
                    tree_widget.populate(
                        self._watcher._last_tree,
                        current_pane_id=self._current_pane_id,
                        status_filter=self._status_filter,
                        name_filter=self._name_filter,
                    )
                self.notify(
                    f"{event.pane_id} → {event.new_status.value}", timeout=3
                )
            else:
                self.notify(msg, timeout=5)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_app.py::test_notification_waiting_trigger_updates_ui tests/test_app.py::test_notification_no_match_shows_raw_toast -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_app.py src/muxpilot/app.py
git commit -m "feat: integrate notification processing into App UI refresh"
```

---

## Task 4: Update example config

**Files:**
- Modify: `config.example.toml`

- [ ] **Step 1: Update example config**

Add to `config.example.toml` in the `[notifications]` section (after `poll_errors`):

```toml
# Regex pattern that triggers WAITING_INPUT status on a pane.
# The notification message must contain both a pane id (e.g. %1) and
# a match for this pattern. Leave empty to disable.
# waiting_trigger_pattern = "WAITING"
```

- [ ] **Step 2: No test needed for docs change — verify file looks correct**

Run: `cat config.example.toml`

- [ ] **Step 3: Commit**

```bash
git add config.example.toml
git commit -m "docs: document waiting_trigger_pattern in example config"
```

---

## Task 5: Full test suite verification

- [ ] **Step 1: Run all watcher tests**

Run: `uv run pytest tests/test_watcher.py tests/test_watcher_config.py -v`

Expected: All PASS

- [ ] **Step 2: Run all app tests**

Run: `uv run pytest tests/test_app.py -v`

Expected: All PASS

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -v`

Expected: All PASS

- [ ] **Step 4: Commit if any fixes were needed**

If any test failed and required fixes, commit them. Otherwise, no commit needed.

---

## Self-Review Checklist

**1. Spec coverage:**
- ✅ Config loading (`waiting_trigger_pattern`) — Task 1
- ✅ Regex matching on notification messages — Task 2
- ✅ Pane id extraction (`%[0-9]+`) — Task 2
- ✅ Status change to `WAITING_INPUT` — Task 2
- ✅ UI refresh on match — Task 3
- ✅ Non-matching messages still show as toasts — Task 3
- ✅ Example config documentation — Task 4

**2. Placeholder scan:**
- No TBD/TODO/"implement later"/"add appropriate error handling" found.
- All test code is concrete and runnable.
- All file paths are exact.

**3. Type consistency:**
- `waiting_trigger_pattern: re.Pattern[str] | None` used consistently.
- `process_notification(message: str) -> TmuxEvent | None` signature is consistent.
- `TmuxEvent` fields (`event_type`, `pane_id`, `old_status`, `new_status`, `message`) match existing usage.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2025-05-03-toast-notification-waiting-status.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
