"""Logging configuration for muxpilot.

Sets up a rotating file handler under ~/.config/muxpilot/muxpilot.log
and reads the log level from config.toml.
"""

from __future__ import annotations

import logging
import logging.handlers
import pathlib
import tomllib


def setup_logging(
    log_path: pathlib.Path | None = None,
    config_path: pathlib.Path | None = None,
) -> None:
    """Configure logging for the muxpilot package.

    Creates a RotatingFileHandler (1 MB, 3 backups) that writes to
    ``~/.config/muxpilot/muxpilot.log`` by default.  The log level is
    read from ``config.toml`` under the ``[logging]`` section (key
    ``level``).  If the file or key is missing, ``INFO`` is used.

    Calling this function more than once is safe – existing handlers
    are not duplicated.
    """
    if log_path is None:
        log_path = pathlib.Path.home() / ".config/muxpilot/muxpilot.log"

    # Ensure parent directory exists
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Determine level from config
    level = logging.INFO
    if config_path is None:
        config_path = pathlib.Path.home() / ".config/muxpilot/config.toml"
    if config_path.exists():
        try:
            with open(config_path, "rb") as f:
                config = tomllib.load(f)
            level_name = config.get("logging", {}).get("level", "INFO")
            level = getattr(logging, level_name.upper(), logging.INFO)
        except Exception:
            level = logging.INFO

    logger = logging.getLogger("muxpilot")
    logger.setLevel(level)

    # Avoid duplicate handlers
    if any(isinstance(h, logging.handlers.RotatingFileHandler) for h in logger.handlers):
        return

    handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=1_048_576,  # 1 MB
        backupCount=3,
        encoding="utf-8",
    )
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
