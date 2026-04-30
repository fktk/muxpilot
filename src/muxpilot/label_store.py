"""TOML-backed label persistence for custom display names."""

from __future__ import annotations

from pathlib import Path

import tomlkit
from tomlkit.toml_document import TOMLDocument


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
        self._doc: TOMLDocument = self._load()

    def get(self, key: str) -> str:
        """Return the custom label for *key*, or empty string if unset."""
        labels = self._doc.get("labels")
        if labels is None:
            return ""
        return labels.get(key, "")  # type: ignore[no-any-return]

    def set(self, key: str, label: str) -> None:
        """Set (or delete if empty) a custom label and persist to disk."""
        if not label:
            self.delete(key)
            return
        if "labels" not in self._doc:
            self._doc.add("labels", tomlkit.table())
        self._doc["labels"][key] = label  # type: ignore[index]
        self._save()

    def delete(self, key: str) -> None:
        """Remove a custom label. No-op if key doesn't exist."""
        labels = self._doc.get("labels")
        if labels is None:
            return
        if key in labels:
            del labels[key]
            self._save()

    def get_theme(self) -> str:
        """Return the stored theme or 'textual-dark' default."""
        app = self._doc.get("app")
        if app is None:
            return "textual-dark"
        return app.get("theme", "textual-dark")  # type: ignore[no-any-return]

    def set_theme(self, theme: str) -> None:
        """Set the theme and persist to disk."""
        if "app" not in self._doc:
            self._doc.add("app", tomlkit.table())
        self._doc["app"]["theme"] = theme  # type: ignore[index]
        self._save()

    def _load(self) -> TOMLDocument:
        if self._path.exists():
            text = self._path.read_text(encoding="utf-8")
            return tomlkit.parse(text)
        return tomlkit.document()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(tomlkit.dumps(self._doc), encoding="utf-8")
