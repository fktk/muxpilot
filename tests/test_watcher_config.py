import pytest
from pathlib import Path
from unittest.mock import MagicMock
from muxpilot.watcher import TmuxWatcher

def test_load_watcher_config(tmp_path):
    # Setup
    config_dir = tmp_path / ".config/muxpilot"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "config.toml"
    
    # TOML literal string to avoid any backslash issue
    config_content = """
[watcher]
prompt_patterns = ["^$ ", "^> "]
error_patterns = ["Error:.*"]
"""
    config_file.write_text(config_content)
    
    # Mock home directory
    with pytest.MonkeyPatch.context() as m:
        m.setattr("pathlib.Path.home", lambda: tmp_path)
        
        client = MagicMock()
        watcher = TmuxWatcher(client)
        
        # Verify patterns are loaded
        assert len(watcher.prompt_patterns) == 2
        assert len(watcher.error_patterns) == 1
        assert watcher.prompt_patterns[0].pattern == "^$ "
        assert watcher.prompt_patterns[1].pattern == "^> "
        assert watcher.error_patterns[0].pattern == "Error:.*"
