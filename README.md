# muxpilot

![muxpilot](https://img.shields.io/badge/status-active-success.svg)
![python](https://img.shields.io/badge/python-3.12+-blue.svg)

**muxpilot** is a TUI (Terminal User Interface) tool for intuitively navigating tmux sessions, windows, and panes.

It is designed specifically for **AI agent orchestration** and managing tasks running simultaneously across multiple panes. It monitors pane output and automatically estimates and visualizes states such as "command running," "waiting for input," and "error occurred."

[日本語版 README はこちら](./README.ja.md)

## ✨ Features

- **🌲 Hierarchical Tree Display**: Displays the tmux `Session → Window → Pane` structure as a tree.
- **⌨️ Keyboard Navigation**: Vim-like keybindings (`j`/`k`) for quickly moving between panes.
- **🔍 Filtering**:
  - `/`: Filter by name (session name, command, path, etc.)
  - `w`: Extract only panes waiting for input (prompt displayed)
  - `e`: Extract only panes with errors
  - `c`: Clear filters and show all
- **👀 Status Monitoring**: Periodically polls each pane's output and automatically assigns the following status icons:

  | Icon | Status | Detection Condition |
  |:---:|---|---|
  | `●` | ACTIVE | Pane output changed since last poll (command running, log output, etc.) |
  | `◌` | IDLE | Not a prompt, but output hasn't changed for more than a certain time (default 10 seconds) |
  | `⏳` | WAITING | Last line matches a prompt pattern and idle time exceeds threshold (waiting for user input) |
  | `🔴` | ERROR | Error pattern (`Traceback`, `Error:`, `FAILED`, etc.) detected in the last 10 lines |
  | `✅` | COMPLETED | Last line matches a prompt pattern and idle time is within threshold (right after command completion) |

  Status is determined in priority order: **ERROR → COMPLETED / WAITING → IDLE → ACTIVE**.

- **🏷️ Custom Labels**: Rename sessions, windows, and panes with the `n` key. Labels are persisted to `~/.config/muxpilot/config.toml`.
- **📋 Detail Panel**: Displays detailed information about the selected pane, such as the running command, current directory, size, and status.

## 🚀 Installation & Launch

You can launch muxpilot using the Python package manager [uv](https://docs.astral.sh/uv/).

### Launch in Local Development Environment

```bash
git clone https://github.com/fktk/muxpilot.git
cd muxpilot
uv run muxpilot
```

### Run Anywhere Without Installation (uvx)

You can also run it directly from GitHub without installation.

```bash
uvx --from git+https://github.com/fktk/muxpilot.git muxpilot
```

## ⚙️ Configuration

You can customize watcher behavior by creating `~/.config/muxpilot/config.toml`:

```toml
[watcher]
prompt_patterns = ['[$>?]\s*$', 'In \[\d+\]: ']
error_patterns = ['(?i)Error|Exception|Traceback|FAILED|panic|Segmentation fault|FATAL']
idle_threshold = 10.0
```

- `prompt_patterns`: Regex list for detecting prompts. **Replaces** the default patterns entirely.
- `error_patterns`: Regex list for detecting errors. **Replaces** the default patterns entirely.
- `idle_threshold`: Seconds before a pane is considered idle.

See `config.example.toml` for more details.

## ⌨️ Keybindings

| Key | Action |
|------|-----------|
| `↑` / `k` | Move cursor up |
| `↓` / `j` | Move cursor down |
| `Enter` | Jump to selected pane (muxpilot continues running in the background) |
| `a` | Collapse / expand all nodes (toggle) |
| `r` | Manual refresh |
| `/` | Toggle filter input on/off |
| `e` | Show only error (🔴) panes |
| `w` | Show only waiting (⏳) panes |
| `c` | Clear filters and show all |
| `n` | Rename the selected node (custom label) |
| `?` | Show help |
| `q` | Quit |

## 💡 Recommended Usage: Dashboard Operation (Command Center)

muxpilot is designed to be **kept running as a dashboard at all times**.
Even when you press Enter to jump to another pane, muxpilot itself does not exit and continues monitoring in the background.

**Recommended Screen Layout**:
Split the tmux screen and keep muxpilot常驻 on the left (or top).
The optimal usage is like a command center: jump from muxpilot to a working pane with `Enter`, and return to the muxpilot pane with tmux shortcuts (e.g., `Prefix + Left Arrow`).

## 🔔 Toast Notifications

muxpilot displays toast notifications in the lower right corner of the screen. These are automatically shown for structural changes such as pane additions/removals and during manual refresh.

### External Notifications

muxpilot monitors a FIFO (named pipe) at `~/.muxpilot/notify` and can receive arbitrary messages from external processes.

```bash
echo "Build complete!" > ~/.muxpilot/notify
```

This allows you to display notifications on muxpilot from shell scripts or CI tools.

## 🛠 Tech Stack

- [libtmux](https://libtmux.git-pull.com/) - Communication with tmux server, hierarchy data retrieval, pane output capture
- [Textual](https://textual.textualize.io/) - Advanced TUI components, UI rendering and polling via asynchronous event loop

## 📄 License

License is not set.
