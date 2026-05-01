import os
import pathlib
import tempfile

import pytest
from pathlib import Path
from unittest.mock import MagicMock
from muxpilot.watcher import TmuxWatcher
from conftest import make_mock_client


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


def test_watcher_config_error_raises():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write("[watcher\n")  # invalid toml
        path = f.name
    client = make_mock_client()
    try:
        # Currently no error is raised; we want it to report.
        watcher = TmuxWatcher(client, config_path=pathlib.Path(path))
        assert watcher._config_error is not None
    finally:
        os.unlink(path)


def test_watcher_config_error_on_bad_regex():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write('[watcher]\nprompt_patterns = ["["]\n')  # invalid regex
        path = f.name
    client = make_mock_client()
    try:
        watcher = TmuxWatcher(client, config_path=pathlib.Path(path))
        assert watcher._config_error is not None
    finally:
        os.unlink(path)


def test_watcher_reads_poll_interval_from_config():
    import tempfile, pathlib
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write('[watcher]\npoll_interval = 0.5\n')
        path = f.name
    client = make_mock_client()
    try:
        watcher = TmuxWatcher(client, config_path=pathlib.Path(path))
        assert watcher.poll_interval == 0.5
    finally:
        import os
        os.unlink(path)


def test_watcher_notify_poll_errors_defaults_to_true():
    client = make_mock_client()
    watcher = TmuxWatcher(client)
    assert watcher.notify_poll_errors is True


def test_watcher_reads_notify_poll_errors_from_config():
    import tempfile, pathlib
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write('[notifications]\npoll_errors = false\n')
        path = f.name
    client = make_mock_client()
    try:
        watcher = TmuxWatcher(client, config_path=pathlib.Path(path))
        assert watcher.notify_poll_errors is False
    finally:
        import os
        os.unlink(path)
