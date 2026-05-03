"""Tests for muxpilot.label_store — TOML-backed theme persistence."""

from __future__ import annotations

from pathlib import Path


from muxpilot.label_store import LabelStore


class TestLabelStoreTheme:
    """Theme get/set operations."""

    def test_get_theme_default(self, tmp_path: Path) -> None:
        store = LabelStore(config_path=tmp_path / "config.toml")
        assert store.get_theme() == "textual-dark"

    def test_set_and_get_theme(self, tmp_path: Path) -> None:
        store = LabelStore(config_path=tmp_path / "config.toml")
        store.set_theme("textual-light")
        assert store.get_theme() == "textual-light"

    def test_theme_persistence(self, tmp_path: Path) -> None:
        """Theme settings should persist across instances."""
        config_path = tmp_path / "config.toml"
        store1 = LabelStore(config_path=config_path)
        store1.set_theme("textual-light")

        store2 = LabelStore(config_path=config_path)
        assert store2.get_theme() == "textual-light"


class TestLabelStoreConfigPreservation:
    """Existing config content must survive theme edits."""

    def test_preserves_comments_and_watcher_section(self, tmp_path: Path) -> None:
        """Setting a theme must not strip TOML comments or unrelated sections."""
        config_path = tmp_path / "config.toml"
        original_text = '''# muxpilot configuration
# Place this file at ~/.config/muxpilot/config.toml

[app]
# UI theme
theme = "textual-dark"

[watcher]
# Polling interval
poll_interval = 2.0

# Prompt patterns
# Default prompt patterns are:
#   '[$>?]\\s*$'
prompt_patterns = [
  '[$>?]\\s*$',
  'In \\[\\d+\\]: ',
]

# Error patterns
error_patterns = [
  '(?i)Error|Exception',
]
'''
        config_path.write_text(original_text, encoding="utf-8")
        store = LabelStore(config_path=config_path)
        store.set_theme("textual-light")

        saved_text = config_path.read_text(encoding="utf-8")
        # Comments must survive
        assert "# muxpilot configuration" in saved_text
        assert "# Polling interval" in saved_text
        assert "# Prompt patterns" in saved_text
        assert "# Error patterns" in saved_text
        # Arrays must survive
        import tomllib
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        assert data["watcher"]["poll_interval"] == 2.0
        assert len(data["watcher"]["prompt_patterns"]) == 2
        assert len(data["watcher"]["error_patterns"]) == 1
        assert data["app"]["theme"] == "textual-light"


class TestLabelStoreTreePanelMaxWidth:
    """Tree panel max-width get operations."""

    def test_get_tree_panel_max_width_default(self, tmp_path: Path) -> None:
        store = LabelStore(config_path=tmp_path / "config.toml")
        assert store.get_tree_panel_max_width() == 60

    def test_get_tree_panel_max_width_from_config(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text('[ui]\ntree_panel_max_width = 80\n')
        store = LabelStore(config_path=config_path)
        assert store.get_tree_panel_max_width() == 80


class TestLabelStoreEdgeCases:
    """Edge case handling."""

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        config_path = tmp_path / "subdir" / "deep" / "config.toml"
        store = LabelStore(config_path=config_path)
        store.set_theme("textual-light")
        assert config_path.exists()
