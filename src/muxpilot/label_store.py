"""TOML-backed theme persistence for muxpilot."""

from __future__ import annotations

from pathlib import Path

import tomlkit
from tomlkit.toml_document import TOMLDocument


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "muxpilot" / "config.toml"


class LabelStore:
    """Reads and writes app settings (theme) to a TOML config file.

    Custom labels are no longer persisted — they are handled in-memory
    by RenameController.
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self._path = config_path or DEFAULT_CONFIG_PATH
        self._doc: TOMLDocument = self._load()

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
