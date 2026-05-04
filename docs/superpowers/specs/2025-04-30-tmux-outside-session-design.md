# muxpilot outside-tmux session launch

## Summary
When muxpilot is started outside a tmux session, it should create a new tmux session named `muxpilot`, launch itself inside that session, and attach the current terminal to it. This removes the friction of having to manually start tmux before launching muxpilot.

## Current Behavior
- `main()` in `app.py` creates `MuxpilotApp` regardless of tmux context.
- Inside `on_mount()`, `is_inside_tmux()` is checked, and only a warning notification is shown when outside tmux.
- The app continues to run outside tmux, which is not useful since it cannot navigate panes.

## Desired Behavior
1. Detect if running outside tmux **before** initializing the TUI.
2. Create a new tmux session named `muxpilot`.
3. Start `python -m muxpilot` (or the current executable) inside that session.
4. Replace the current process with `tmux attach -t muxpilot`, so the user is seamlessly attached to the new session.

## Design Details

### Entry Point Change (`src/muxpilot/app.py::main`)
Insert tmux-outside detection at the very top of `main()`:

```python
def main() -> None:
    """Entry point for the muxpilot CLI."""
    client = TmuxClient()
    if not client.is_inside_tmux():
        session_name = "muxpilot"
        try:
            subprocess.run(
                ["tmux", "new-session", "-s", session_name, "-d",
                 sys.executable, "-m", "muxpilot"],
                check=True,
            )
        except subprocess.CalledProcessError:
            # Session already exists or another tmux error; just try to attach
            pass
        os.execlp("tmux", "tmux", "attach", "-t", session_name)

    # Normal tmux-inside flow
    app = MuxpilotApp()
    ...
```

### Behavior Notes
- If a session named `muxpilot` already exists, `new-session` will fail. We ignore the error and attempt to attach anyway, which is the correct fallback.
- `os.execlp` replaces the current process, so no code after it executes.
- `sys.executable` ensures the same Python interpreter is used, preserving virtualenv/uv context.

## Testing Plan
- Add tests in `tests/test_app.py` using `unittest.mock` to:
  1. Mock `TmuxClient.is_inside_tmux` returning `False`, then verify `subprocess.run` and `os.execlp` are called with expected arguments.
  2. Mock `is_inside_tmux` returning `True`, then verify `MuxpilotApp.run()` is called normally.

## Files to Modify
- `src/muxpilot/app.py` — add early-exit tmux bootstrap logic in `main()`.
- `tests/test_app.py` — add tests for outside-tmux bootstrap path.

## Risks / Edge Cases
- `tmux` binary not found → `FileNotFoundError` from `subprocess.run`. This is acceptable; the user sees a normal shell error.
- Session already exists → handled by `except subprocess.CalledProcessError`.
- Nested attach (already attached to another tmux session, but `TMUX` env var not set for some reason) → tmux will handle it or error out normally.
