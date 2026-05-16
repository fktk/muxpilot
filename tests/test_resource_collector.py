"""Tests for ResourceCollector."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import psutil
import pytest

from muxpilot.resource_collector import ResourceCollector, ResourceInfo


def test_get_resources_returns_resource_info():
    collector = ResourceCollector()
    mock_proc = MagicMock(spec=psutil.Process)
    mock_proc.pid = 9999
    mock_proc.cpu_times.return_value = MagicMock(user=100.0, system=50.0)
    mock_proc.memory_info.return_value = MagicMock(rss=128_000_000)  # 128 MB
    mock_proc.children.return_value = []

    with (
        patch("muxpilot.resource_collector.psutil.Process", return_value=mock_proc),
        patch("muxpilot.resource_collector.time.monotonic", side_effect=[1.0, 2.0]),
    ):
        # First call: caches, returns None (need two samples)
        result1 = collector.get_resources(9999)
        assert result1 is None

        # Second call: cpu usage went from (100+50=150) to (101+51=152)
        # delta = 2 sec CPU, elapsed = 1 sec -> 200% -> capped at 100%
        mock_proc.cpu_times.return_value = MagicMock(user=101.0, system=51.0)
        result2 = collector.get_resources(9999)
        assert result2 is not None
        assert result2.cpu_percent == 100.0  # capped
        assert result2.memory_rss_kb == 125000  # 128_000_000 / 1024


def test_get_resources_includes_children():
    collector = ResourceCollector()
    main_mock = MagicMock(spec=psutil.Process)
    main_mock.pid = 100
    main_mock.cpu_times.return_value = MagicMock(user=10.0, system=5.0)
    main_mock.memory_info.return_value = MagicMock(rss=64_000_000)

    child = MagicMock(spec=psutil.Process)
    child.pid = 101
    child.cpu_times.return_value = MagicMock(user=2.0, system=1.0)
    child.memory_info.return_value = MagicMock(rss=32_000_000)

    main_mock.children.return_value = [child]

    with (
        patch("muxpilot.resource_collector.psutil.Process", return_value=main_mock),
        patch("muxpilot.resource_collector.time.monotonic", side_effect=[0.0, 0.1, 1.0, 1.1]),
    ):
        first = collector.get_resources(100)
        assert first is None

        main_mock.cpu_times.return_value = MagicMock(user=10.1, system=5.05)
        child.cpu_times.return_value = MagicMock(user=2.02, system=1.01)

        second = collector.get_resources(100)
        assert second is not None
        # RSS: 64MB + 32MB = 96MB -> 93750 KB
        assert second.memory_rss_kb == 93750
        assert 0 <= second.cpu_percent <= 100.0


def test_get_resources_returns_none_on_error():
    collector = ResourceCollector()
    with patch("muxpilot.resource_collector.psutil.Process", side_effect=psutil.NoSuchProcess(9999)):
        result = collector.get_resources(9999)
        assert result is None


def test_get_resources_handles_access_denied():
    collector = ResourceCollector()
    with patch("muxpilot.resource_collector.psutil.Process", side_effect=psutil.AccessDenied()):
        result = collector.get_resources(9999)
        assert result is None


def test_get_resources_empty_cache_on_first_call():
    collector = ResourceCollector()
    assert collector._cache == {}
