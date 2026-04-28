import tomllib
import pathlib
import os
import re
from typing import List

# Assume these exist or will be defined
DEFAULT_PROMPT_PATTERNS = []
DEFAULT_ERROR_PATTERNS = []
DEFAULT_IDLE_THRESHOLD = 1.0

# Placeholder types for TmuxClient, PaneActivity, TmuxTree
class TmuxClient: pass
class PaneActivity: pass
class TmuxTree: pass

class TmuxWatcher:
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
