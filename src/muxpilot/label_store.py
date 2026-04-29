"""TOML-backed label persistence for custom display names."""

from __future__ import annotations

import tomllib
from pathlib import Path

import tomli_w


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "muxpilot" / "config.toml"


class LabelStore:
    """Reads and writes custom labels to a TOML config file.

    Labels are stored under the [labels] section with flat string keys:
      - "session_name" for sessions
      - "session_name.window_index" for windows
      - "session_name.window_index.pane_index" for panes
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self._path = config_path or DEFAULT_CONFIG_PATH
        self._data: dict = self._load()

    def get(self, key: str) -> str:
        """Return the custom label for *key*, or empty string if unset."""
        return self._data.get("labels", {}).get(key, "")

    def set(self, key: str, label: str) -> None:
        """Set (or delete if empty) a custom label and persist to disk."""
        if not label:
            self.delete(key)
            return
        self._data.setdefault("labels", {})[key] = label
        self._save()

    def delete(self, key: str) -> None:
        """Remove a custom label. No-op if key doesn't exist."""
        labels = self._data.get("labels", {})
        if key in labels:
            del labels[key]
            self._save()

    def get_theme(self) -> str:
        """Return the stored theme or 'textual-dark' default."""
        return self._data.get("app", {}).get("theme", "textual-dark")

    def set_theme(self, theme: str) -> None:
        """Set the theme and persist to disk."""
        self._data.setdefault("app", {})["theme"] = theme
        self._save()

    def _load(self) -> dict:
        if self._path.exists():
            with open(self._path, "rb") as f:
                return tomllib.load(f)
        return {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "wb") as f:
            tomli_w.dump(self._data, f)
