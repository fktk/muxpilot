import pytest
from unittest.mock import patch, mock_open
from muxpilot.watcher import TmuxWatcher
from muxpilot.tmux_client import TmuxClient

@patch("tomllib.load")
@patch("builtins.open", new_callable=mock_open, read_data="""
[watcher]
prompt_patterns = ["^CustomPrompt>\\s*$"]
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
