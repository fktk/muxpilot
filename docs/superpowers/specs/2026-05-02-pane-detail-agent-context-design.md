# Pane Detail Panel — Agent Context Design

## Summary

Refactor the pane detail panel to display information optimized for users running multiple coding agents (Claude Code, OpenCode, Copilot CLI, etc.) in parallel across different panes. The goal is to make it immediately obvious **which repository, branch, and task each pane is working on**, and whether the agent is still alive.

## Changes

### 1. `PaneInfo` model (`src/muxpilot/models.py`)

- Add `pane_title: str = ""` field.
- Update `display_label` to prefer `pane_title` when set, falling back to `custom_label`, then the existing command+path heuristic.
- Add `repo_name: str = ""` and `branch: str = ""` fields (populated by TmuxClient).
- Add `idle_seconds: float = 0.0` field (populated by the watcher).

### 2. `PaneActivity` model (`src/muxpilot/models.py`)

- Add `recent_lines: list[str] = field(default_factory=list)` to store the last N captured lines for the preview.

### 3. `TmuxClient` (`src/muxpilot/tmux_client.py`)

- In `get_tree()`, read `pane.pane_title` from libtmux and set it on `PaneInfo`.
- Add helper `_get_git_info(path: str) -> dict[str, str]` that runs `git rev-parse --show-toplevel` and `git branch --show-current` to extract:
  - `repo_name`: basename of the git toplevel directory, or `""` if not a repo.
  - `branch`: current branch name, or `""` if not a repo / detached HEAD.
- Populate `PaneInfo` with `repo_name` and `branch` fields.
- Add `set_pane_title(pane_id: str, title: str) -> bool` that calls `tmux select-pane -t <pane_id> -T <title>` via libtmux.

### 4. `TmuxWatcher` (`src/muxpilot/watcher.py`)

- In `poll()`, after capturing pane content, store the last `preview_lines` (default 5) into `PaneActivity.recent_lines`.
- Pass `preview_lines` count as a constructor argument (default 5).
- Set `pane.idle_seconds` from the activity tracker before returning the tree.

### 5. `DetailPanel` (`src/muxpilot/widgets/detail_panel.py`)

Rewrite `show_pane()` to show:

```
── Pane ──

  Title:        <pane_title or custom_label or "—">
  Repository:   <repo_name or "—">
  Branch:       <branch or "—">
  Command:      <full_command or current_command>
  Path:         <shortened current_path>
  Size:         <width>×<height>
  Active:       Yes / No
  Status:       [icon] <status> (<idle_seconds>s idle)

── Recent Output ──
  <line 1>
  <line 2>
  <line 3>
  <line 4>
  <line 5>

  Window:       <window_name> (#<index>)
  Session:      <session_name>
```

Display rules:
- If `pane_title` is empty, show `"—"`.
- If not inside a git repo, show `"—"` for Repository and Branch.
- `idle_seconds` is shown only when `status` is `IDLE` or `WAITING_INPUT`.
- Recent output lines are joined and wrapped to fit panel width. Empty lines are shown as `"(blank)"` dimmed.
- `ERROR` status is highlighted in red (`$error` color).
- `WAITING_INPUT` status is highlighted in yellow (`$warning` color).

### 6. Tests

- `test_models.py`: Add `pane_title` and `idle_seconds` to pane fixtures; verify `display_label` priority (pane_title > custom_label > heuristic).
- `test_tmux_client.py`: Mock libtmux pane with `pane_title`; mock git subprocess calls; assert `repo_name` and `branch` are populated.
- `test_watcher.py`: Assert `recent_lines` is stored in `PaneActivity` and `idle_seconds` is set on `PaneInfo`.
- `test_app.py`: Update detail panel assertions to match new format.
- `test_detail_panel.py` (if exists): Update expected markup.

## Data Flow

```
TmuxClient.get_tree()
  ├── reads pane.pane_title from libtmux
  ├── runs git commands per pane path
  └── returns PaneInfo(..., pane_title=..., repo_name=..., branch=...)

TmuxWatcher.poll()
  ├── captures pane content
  ├── stores last N lines in PaneActivity.recent_lines
  ├── calculates idle_seconds
  └── sets pane.idle_seconds on PaneInfo

DetailPanel.show_pane()
  └── renders all fields including preview and idle time
```

## Edge Cases

- **Non-git directories**: `repo_name` and `branch` show `"—"`; no subprocess errors leak.
- **Detached HEAD**: `branch` shows `"(detached)"` or `""` depending on `git branch --show-current` behavior.
- **Pane without title**: Falls back to `custom_label`, then existing heuristic.
- **Empty recent output**: Shows `"(no output)"` dimmed instead of blank section.
- **Permission denied on git**: Caught and treated as non-repo.

### 3.5 Rename flow update

- Change `RenameController` so that `finish()` calls `TmuxClient.set_pane_title()` instead of writing to `LabelStore`.
- Remove `custom_label` overlay logic from `RenameController`; the rename now directly sets the tmux pane title.
- Tree view labels will reflect the new pane title on the next poll.

## Out of Scope

- Automatically setting pane titles from agent prompts. The user can already use tmux’s `set-option -p pane_title "..."` or muxpilot’s rename (`n` key) which now targets `pane_title` directly.
- Fetching git status (changed file count, last commit). Too expensive to run per pane per poll.
- Parsing agent-specific output patterns beyond the existing error/prompt detection.

## Success Criteria

- [ ] Selecting a pane shows its `pane_title`, repository, branch, command, idle time, and a 5-line output preview.
- [ ] Tree view labels prefer `pane_title` when available.
- [ ] All existing tests pass; new tests cover the added fields and rendering.
- [ ] No measurable slowdown in polling (< 50 ms added per pane with git commands).
