"""Tests for muxpilot.label_store — TOML-backed label persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from muxpilot.label_store import LabelStore


class TestLabelStoreGetSetDelete:
    """Basic get/set/delete operations."""

    def test_get_returns_empty_string_when_no_label(self, tmp_path: Path) -> None:
        store = LabelStore(config_path=tmp_path / "config.toml")
        assert store.get("myproject") == ""

    def test_set_and_get(self, tmp_path: Path) -> None:
        store = LabelStore(config_path=tmp_path / "config.toml")
        store.set("myproject", "🚀 Main")
        assert store.get("myproject") == "🚀 Main"

    def test_set_overwrites_existing(self, tmp_path: Path) -> None:
        store = LabelStore(config_path=tmp_path / "config.toml")
        store.set("myproject", "old")
        store.set("myproject", "new")
        assert store.get("myproject") == "new"

    def test_delete_removes_label(self, tmp_path: Path) -> None:
        store = LabelStore(config_path=tmp_path / "config.toml")
        store.set("myproject", "label")
        store.delete("myproject")
        assert store.get("myproject") == ""

    def test_delete_nonexistent_key_is_noop(self, tmp_path: Path) -> None:
        store = LabelStore(config_path=tmp_path / "config.toml")
        store.delete("nonexistent")  # should not raise

    def test_set_window_label(self, tmp_path: Path) -> None:
        store = LabelStore(config_path=tmp_path / "config.toml")
        store.set("myproject.1", "Editor")
        assert store.get("myproject.1") == "Editor"

    def test_set_pane_label(self, tmp_path: Path) -> None:
        store = LabelStore(config_path=tmp_path / "config.toml")
        store.set("myproject.1.0", "vim server")
        assert store.get("myproject.1.0") == "vim server"


class TestLabelStorePersistence:
    """File persistence tests."""

    def test_labels_persist_across_instances(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        store1 = LabelStore(config_path=config_path)
        store1.set("myproject", "persisted")

        store2 = LabelStore(config_path=config_path)
        assert store2.get("myproject") == "persisted"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        config_path = tmp_path / "subdir" / "deep" / "config.toml"
        store = LabelStore(config_path=config_path)
        store.set("test", "value")
        assert config_path.exists()

    def test_loads_existing_config_without_labels_section(self, tmp_path: Path) -> None:
        """A config.toml without [labels] should not crash."""
        config_path = tmp_path / "config.toml"
        config_path.write_text('[other]\nkey = "value"\n')
        store = LabelStore(config_path=config_path)
        assert store.get("anything") == ""

    def test_preserves_other_sections(self, tmp_path: Path) -> None:
        """Setting a label should not destroy other TOML sections."""
        config_path = tmp_path / "config.toml"
        config_path.write_text('[other]\nkey = "value"\n')
        store = LabelStore(config_path=config_path)
        store.set("myproject", "label")

        import tomllib
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        assert data["other"]["key"] == "value"
        assert data["labels"]["myproject"] == "label"


class TestLabelStoreEdgeCases:
    """Edge case handling."""

    def test_session_name_with_dots(self, tmp_path: Path) -> None:
        """Session names containing dots should work (TOML quoted keys)."""
        store = LabelStore(config_path=tmp_path / "config.toml")
        store.set("my.project", "dotted")
        assert store.get("my.project") == "dotted"

    def test_empty_label_treated_as_delete(self, tmp_path: Path) -> None:
        """Setting a label to empty string should delete it."""
        store = LabelStore(config_path=tmp_path / "config.toml")
        store.set("myproject", "something")
        store.set("myproject", "")
        assert store.get("myproject") == ""
