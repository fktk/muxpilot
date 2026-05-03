# Toast Notification → WAITING Status Design

## Summary
Allow external processes to trigger a `WAITING_INPUT` status change on a specific tmux pane by sending a message through the FIFO notification channel. The message must contain the target pane's `pane_id` and match a user-configurable regex pattern.

## Motivation
In AI agent orchestration workflows, a running process in a tmux pane may finish its task and want to signal that it is waiting for the next instruction. Instead of relying solely on polling-based prompt detection, we want an explicit push mechanism via the existing FIFO notification channel.

## Design

### 1. Config Schema

Add a new `[notifications]` subsection in `~/.config/muxpilot/config.toml`:

```toml
[notifications]
# Existing setting
poll_errors = true

# NEW: Regex pattern that a notification message must match to trigger WAITING.
# The message must also contain a pane_id (e.g. %1, %42).
# Default: empty string (disabled)
waiting_trigger_pattern = "WAITING"
```

- `waiting_trigger_pattern`: A Python regular expression string. If empty or omitted, the feature is disabled.

### 2. Message Format Convention

No strict envelope format. The message is scanned for:
1. A pane id token matching `%[0-9]+`.
2. A substring matching `waiting_trigger_pattern`.

Both must be present in the same message. Example valid messages:
- `Task complete %3 WAITING`
- `%42 is WAITING for input`

### 3. Watcher Extension

Introduce `TmuxWatcher.process_notification(message: str) -> TmuxEvent | None`.

Responsibilities:
1. Skip if `waiting_trigger_pattern` is empty.
2. Search `message` for the first token matching `%[0-9]+` → `pane_id`.
3. Search `message` for a match against `waiting_trigger_pattern`.
4. If both are found and the pane exists in `self.activities`:
   - Set `self.activities[pane_id].status = PaneStatus.WAITING_INPUT`.
   - Return a `TmuxEvent(event_type="status_changed", pane_id=pane_id, old_status=..., new_status=PaneStatus.WAITING_INPUT, message=...)`.
5. Otherwise return `None`.

Edge cases:
- Pane not currently tracked → `None` (the next poll will add it; the user can resend).
- Pane already `WAITING_INPUT` → still returns the event so the UI refreshes and the user gets feedback.

### 4. App Integration

In `MuxpilotApp._check_notifications()`:

```python
async def _check_notifications(self) -> None:
    while True:
        msg = self._notify_channel.receive()
        if msg is None:
            break
        # NEW: try watcher-driven status change first
        event = self._watcher.process_notification(msg)
        if event:
            self._apply_labels(self._watcher._last_tree)
            tree_widget = self.query_one("#tmux-tree", TmuxTreeView)
            tree_widget.populate(
                self._watcher._last_tree,
                current_pane_id=self._current_pane_id,
                status_filter=self._status_filter,
                name_filter=self._name_filter,
            )
            self.notify(f"{event.pane_id} → {event.new_status.value}", timeout=3)
        else:
            self.notify(msg, timeout=5)
```

If `process_notification` produces an event, the UI is refreshed immediately and a confirmation toast is shown instead of the raw message.

### 5. Data Flow

```
External process
      │
      ▼
  echo "done %3 WAITING" > ~/.config/muxpilot/notify
      │
      ▼
NotifyChannel._read_loop  ──►  queue
      │
      ▼
App._check_notifications
      │
      ├──► watcher.process_notification(msg)
      │         ├── extract pane_id %3
      │         ├── match pattern /WAITING/
      │         ├── set activities["%3"].status = WAITING_INPUT
      │         └── return TmuxEvent
      │
      └──► refresh tree widget + confirm toast
```

### 6. Testing Strategy

Unit tests in `test_watcher.py` (or `test_watcher_config.py`):
- Given a watcher with `waiting_trigger_pattern = "WAITING"`:
  - Message `"%1 WAITING"` → returns event, activity status updated.
  - Message `"no pane id WAITING"` → returns `None`.
  - Message `"%1 something else"` → returns `None`.
  - Message `"%1 WAITING"` for unknown pane → returns `None`.

Integration in `test_app.py`:
- Mock `NotifyChannel` to enqueue a waiting message.
- Assert that `_check_notifications` calls `process_notification` and refreshes the tree.

### 7. Backward Compatibility

- Default `waiting_trigger_pattern = ""` disables the feature entirely.
- Existing notifications that do not match behave exactly as before.
- No schema or API breaking changes.

## Open Questions

None at this time.
