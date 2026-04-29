# Watcher Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to customize `TmuxWatcher` status detection patterns via `~/.config/muxpilot/config.toml`.

**Architecture:** Modify `TmuxWatcher.__init__` to load patterns from a TOML file. The loaded patterns will be compiled using `re.compile()` and merged with default patterns stored in `watcher.py`.

**Tech Stack:** Python 3.11+ (`tomllib`), `re`.

---

### Task 1: Create a test for configuration loading

**Files:**
- Create: `tests/test_watcher_config.py`

- [ ] **Step 1: Write a test for loading config**

```python
import pytest
from unittest.mock import patch, mock_open
from muxpilot.watcher import TmuxWatcher
from muxpilot.tmux_client import TmuxClient

@patch("tomllib.load")
@patch("builtins.open", new_callable=mock_open, read_data="""
[watcher]
prompt_patterns = ["^CustomPrompt>\\\\s*$"]
error_patterns = ["CustomCriticalError"]
""")
def test_watcher_config_loading(mock_file, mock_toml):
    mock_toml.return_value = {
        "watcher": {
            "prompt_patterns": ["^CustomPrompt>\\s*$"],
            "error_patterns": ["CustomCriticalError"]
        }
    }
    client = TmuxClient() # Simplified for test
    watcher = TmuxWatcher(client)
    
    # Check if patterns are merged
    # Default prompt patterns length: 7 (as per src/muxpilot/watcher.py)
    # Default error patterns length: 7
    assert len(watcher.prompt_patterns) == 8
    assert len(watcher.error_patterns) == 8
    assert watcher.prompt_patterns[-1].pattern == "^CustomPrompt>\\s*$"
    assert watcher.error_patterns[-1].pattern == "CustomCriticalError"
```

- [ ] **Step 2: Commit**

```bash
git add tests/test_watcher_config.py
git commit -m "test: add test for watcher config loading"
```

### Task 2: Modify `TmuxWatcher` to load config

**Files:**
- Modify: `src/muxpilot/watcher.py`

- [ ] **Step 1: Update `TmuxWatcher.__init__`**

```python
import tomllib
import pathlib
import os

# ... inside class TmuxWatcher:

    def __init__(
        self,
        client: TmuxClient,
        idle_threshold: float = DEFAULT_IDLE_THRESHOLD,
        capture_lines: int = 30,
    ) -> None:
        self.client = client
        self.idle_threshold = idle_threshold
        self.capture_lines = capture_lines
        self.activities: dict[str, PaneActivity] = {}
        
        # Load config
        self.prompt_patterns = list(DEFAULT_PROMPT_PATTERNS)
        self.error_patterns = list(DEFAULT_ERROR_PATTERNS)
        
        config_path = pathlib.Path.home() / ".config/muxpilot/config.toml"
        if config_path.exists():
            try:
                with open(config_path, "rb") as f:
                    config = tomllib.load(f)
                    watcher_cfg = config.get("watcher", {})
                    
                    for p in watcher_cfg.get("prompt_patterns", []):
                        self.prompt_patterns.append(re.compile(p))
                    for p in watcher_cfg.get("error_patterns", []):
                        self.error_patterns.append(re.compile(p))
            except Exception as e:
                print(f"Warning: Failed to load config from {config_path}: {e}")

        self._last_tree: TmuxTree | None = None
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_watcher_config.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/muxpilot/watcher.py tests/test_watcher_config.py
git commit -m "feat: implement watcher pattern customization via config.toml"
```
