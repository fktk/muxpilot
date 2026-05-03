"""Common helpers for test_app_* modules."""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock

from muxpilot.app import MuxpilotApp
from muxpilot.controllers import RenameController
from muxpilot.notify_channel import NotifyChannel
from muxpilot.watcher import TmuxWatcher

from conftest import make_mock_client, make_mock_notify_channel


def _patched_app(tree=None, current_pane_id=None, label_store=None, config_error=None, config_path=None):
    """Create a MuxpilotApp with a mocked TmuxClient/Watcher."""
    mock_client = make_mock_client(tree=tree, current_pane_id=current_pane_id)
    app = MuxpilotApp(config_path=config_path)
    app._client = mock_client
    app._rename_controller = RenameController(mock_client)
    app._watcher = TmuxWatcher(mock_client, config_path=pathlib.Path("/nonexistent-muxpilot-config"))
    app._notify_channel = make_mock_notify_channel()
    if config_error is not None:
        app._watcher._config_error = config_error
        app._notify_config_error()
    if label_store is not None:
        app._label_store = label_store
    return app
