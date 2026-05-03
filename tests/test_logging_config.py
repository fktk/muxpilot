"""Tests for logging configuration."""

from __future__ import annotations

import logging
import pathlib
from unittest.mock import patch

import pytest

from muxpilot.logging_config import setup_logging


@pytest.fixture(autouse=True)
def clear_muxpilot_handlers():
    """Remove all handlers from the muxpilot logger between tests."""
    logger = logging.getLogger("muxpilot")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    yield


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_default_setup(self, tmp_path):
        """Default setup should use INFO level and create a rotating file handler."""
        log_path = tmp_path / "muxpilot.log"
        setup_logging(log_path=log_path)

        root = logging.getLogger("muxpilot")
        assert root.level == logging.INFO
        assert any(
            isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers
        )

    def test_level_from_config(self, tmp_path):
        """Should read level from config file if present."""
        log_path = tmp_path / "muxpilot.log"
        config_path = tmp_path / "config.toml"
        config_path.write_text("[logging]\nlevel = 'DEBUG'\n")

        setup_logging(log_path=log_path, config_path=config_path)

        root = logging.getLogger("muxpilot")
        assert root.level == logging.DEBUG

    def test_default_level_when_no_config(self, tmp_path):
        """Should default to INFO when no config file exists."""
        log_path = tmp_path / "muxpilot.log"
        config_path = tmp_path / "nonexistent.toml"

        setup_logging(log_path=log_path, config_path=config_path)

        root = logging.getLogger("muxpilot")
        assert root.level == logging.INFO

    def test_no_duplicate_handlers(self, tmp_path):
        """Calling setup_logging twice should not add duplicate handlers."""
        log_path = tmp_path / "muxpilot.log"
        setup_logging(log_path=log_path)
        setup_logging(log_path=log_path)

        root = logging.getLogger("muxpilot")
        rotating_handlers = [
            h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert len(rotating_handlers) == 1

    def test_creates_parent_directory(self, tmp_path):
        """Should create parent directory for log file if it doesn't exist."""
        log_path = tmp_path / "deep" / "nested" / "muxpilot.log"
        setup_logging(log_path=log_path)

        assert log_path.parent.exists()

    def test_invalid_level_falls_back_to_info(self, tmp_path):
        """Should fall back to INFO when config level is invalid."""
        log_path = tmp_path / "muxpilot.log"
        config_path = tmp_path / "config.toml"
        config_path.write_text("[logging]\nlevel = 'INVALID'\n")

        setup_logging(log_path=log_path, config_path=config_path)

        root = logging.getLogger("muxpilot")
        assert root.level == logging.INFO

    def test_actual_handler(self, tmp_path):
        """Integration test: actual handler should write to file."""
        log_path = tmp_path / "muxpilot.log"
        setup_logging(log_path=log_path)

        logger = logging.getLogger("muxpilot.test")
        logger.info("test message")
        logging.shutdown()

        assert log_path.exists()
        content = log_path.read_text()
        assert "test message" in content
