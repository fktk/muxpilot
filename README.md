# muxpilot

![muxpilot](https://img.shields.io/badge/status-active-success.svg)
![python](https://img.shields.io/badge/python-3.12+-blue.svg)

**muxpilot** is a TUI (Terminal User Interface) tool for intuitively navigating tmux sessions, windows, and panes.

It is designed specifically for **AI agent orchestration** and managing tasks running simultaneously across multiple panes. It monitors pane output and automatically estimates and visualizes states such as "command running," "waiting for input," "error occurred," and "idle."

[日本語版 README はこちら](./README.ja.md)

## ✨ Features

- **🌲 Hierarchical Tree Display**: Displays the tmux `Session → Window → Pane` structure as a tree.
- **⌨️ Keyboard Navigation**: Vim-like keybindings (`j`/`k`) for quickly moving between panes.
- **🔍 Filtering**:
  - `/`: Filter by name (session name, command, path, etc.)
  - `a`: Clear filters and show all
- **👀 Status Monitoring**: Periodically polls each pane's output and automatically assigns one of four status icons:

  | Icon | Status | Detection Condition |
  |:---:|---|---|
  | 🚶/🏃 | ACTIVE | Pane output changed since last poll, or no prompt/error/idle detected (command running, log output, etc.) |
  | ✋ | WAITING | Last line matches a prompt pattern (waiting for user input) |
  | 🚨 | ERROR | Error pattern (`Traceback`, `Error:`, `FAILED`, etc.) detected in the last 10 lines |
  | 🛌 | IDLE | No output change for longer than the configured idle threshold |

  Status is determined in priority order: **ERROR → WAITING → IDLE → ACTIVE**.  
  Additionally, once a pane leaves `ACTIVE`, it keeps its current status until new output arrives (hysteresis).

- **🏷️ Rename Node**: Rename the selected session, window, or pane with the `n` key. For panes, this updates the native tmux title (visible to other tmux clients as well).
- **📋 Detail Panel**: Displays detailed information about the selected pane, such as the running command, full command line, current directory, git repo/branch, status, idle time, and recent output lines.

## 🚀 Installation & Launch

You can launch muxpilot using the Python package manager [uv](https://docs.astral.sh/uv/).

### Launch in Local Development Environment

```bash
git clone https://github.com/fktk/muxpilot.git
cd muxpilot
uv run muxpilot
```

If you run muxpilot **outside** of a tmux session, it will automatically create a new tmux session named `muxpilot` and attach to it.

### Run Anywhere Without Installation (uvx)

You can also run it directly from GitHub without installation.

```bash
uvx --from git+https://github.com/fktk/muxpilot.git muxpilot
```

## ⚙️ Configuration

You can customize muxpilot by creating `~/.config/muxpilot/config.toml`. Specifying any list option **completely replaces** the defaults (they are not merged).

```toml
[app]
theme = "textual-dark"  # or "textual-light", "nord", "gruvbox"

[watcher]
poll_interval = 2.0       # Seconds between polls
idle_threshold = 10.0     # Seconds of no output before a pane is considered idle
prompt_patterns = [
    '[$>?]\\s*$',
    'In \\[\\d+\\]: ',
    '(?i)\\(y/n\\)',
]
error_patterns = [
    '(?i)Error|Exception|Traceback|FAILED|panic|Segmentation fault|FATAL',
]

[ui]
tree_panel_max_width = 60    # Maximum width of the tree panel in characters
sidebar_hide_threshold = 80  # Hide detail panel when terminal is at or below this width

[notifications]
poll_errors = true                     # Show toast when tmux polling fails
notification_cooldown = 5.0            # Seconds to keep WAITING status after FIFO trigger
waiting_trigger_pattern = "WAITING"    # Regex that triggers WAITING status via FIFO

[logging]
level = "INFO"  # DEBUG, INFO, WARNING, or ERROR for ~/.config/muxpilot/muxpilot.log
```

- `prompt_patterns`: Regex list for detecting prompts.
- `error_patterns`: Regex list for detecting errors.
- `poll_interval`: How often to poll tmux for updates.
- `idle_threshold`: How long a pane must be silent before it becomes `IDLE`.
- `tree_panel_max_width`: Caps the width of the left tree panel.
- `sidebar_hide_threshold`: Hides the detail panel when the terminal width is at or below this value. Set to `0` to disable.
- `poll_errors`: Set to `false` to suppress "tmux poll failed" toast messages.
- `notification_cooldown`: How long to preserve a notification-triggered `WAITING` status before allowing content changes to clear it.
- `waiting_trigger_pattern`: When an external FIFO message contains both a pane id (e.g. `%1`) and a match for this pattern, that pane is forced to `WAITING` status.
- `level`: Log level for the muxpilot log file (`~/.config/muxpilot/muxpilot.log`).

See `config.example.toml` for more details.

## ⌨️ Keybindings

| Key | Action |
|------|-----------|
| `↑` / `k` | Move cursor up |
| `↓` / `j` | Move cursor down |
| `Enter` | Jump to selected pane (muxpilot continues running in the background) |
| `/` | Toggle name filter input on/off |
| `a` | Clear filters and show all |
| `n` | Rename the selected node |
| `x` | Kill the selected pane |
| `?` | Show help |
| `q` | Quit |

## 💡 Recommended Usage: Dashboard Operation (Command Center)

muxpilot is designed to be **kept running as a dashboard at all times**.
Even when you press Enter to jump to another pane, muxpilot itself does not exit and continues monitoring in the background.

**Recommended Screen Layout**:
Split the tmux screen and keep muxpilot常驻 on the left (or top).
The optimal usage is like a command center: jump from muxpilot to a working pane with `Enter`, and return to the muxpilot pane with tmux shortcuts (e.g., `Prefix + Left Arrow`).

## 🔔 Toast Notifications

muxpilot displays toast notifications in the lower right corner of the screen. These are shown for external FIFO messages and polling errors.

### External Notifications

muxpilot monitors a FIFO (named pipe) at `~/.config/muxpilot/notify` and can receive messages from external processes.

```bash
echo "Build complete!" > ~/.config/muxpilot/notify
```

Messages are displayed as toast notifications. Additionally, if you set `waiting_trigger_pattern` in the config, a message that contains **both** a pane id (e.g. `%1`) and a match for the pattern will force that pane to `WAITING` status. For example:

```bash
echo "%42 WAITING" > ~/.config/muxpilot/notify
```

## 🛠 Tech Stack

- [libtmux](https://libtmux.git-pull.com/) - Communication with tmux server, hierarchy data retrieval, pane output capture
- [Textual](https://textual.textualize.io/) - Advanced TUI components, UI rendering and polling via asynchronous event loop

## 📄 License

License is not set.
