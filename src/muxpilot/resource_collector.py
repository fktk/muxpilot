"""CPU and memory resource collection for tmux panes."""

from __future__ import annotations

import time
from dataclasses import dataclass

import psutil


@dataclass
class ResourceInfo:
    cpu_percent: float
    memory_rss_kb: int


@dataclass
class _ProcessCache:
    cpu_times: object
    time: float


class ResourceCollector:
    """Collects CPU and memory usage for a process and its direct children."""

    def __init__(self) -> None:
        self._cache: dict[int, _ProcessCache] = {}

    def get_resources(self, main_pid: int) -> ResourceInfo | None:
        """Get CPU% and memory RSS for the given PID and its direct children.

        Returns None on first call (needs a baseline), or when the process
        does not exist or is inaccessible.
        """
        try:
            main = psutil.Process(main_pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            self._cache.pop(main_pid, None)
            return None

        try:
            main_cpu = self._calc_cpu(main_pid, main)
            main_mem = main.memory_info().rss

            child_cpu: float = 0.0
            child_mem: int = 0
            try:
                children = main.children(recursive=False)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
                children = []
            for child in children:
                try:
                    child_cpu += self._calc_cpu(child.pid, child) or 0.0
                    child_mem += child.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
                    pass

            if main_cpu is None:
                return None

            return ResourceInfo(
                cpu_percent=min(main_cpu + child_cpu, 100.0),
                memory_rss_kb=(main_mem + child_mem) // 1024,
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
            self._cache.pop(main_pid, None)
            return None

    def _calc_cpu(self, pid: int, proc: psutil.Process) -> float | None:
        """Calculate CPU% since the last call. Returns None on first call."""
        now = time.monotonic()
        try:
            times = proc.cpu_times()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            self._cache.pop(pid, None)
            return None

        prev = self._cache.get(pid)
        if prev is None:
            self._cache[pid] = _ProcessCache(cpu_times=times, time=now)
            return None

        delta_cpu = (times.user + times.system) - (prev.cpu_times.user + prev.cpu_times.system)
        delta_time = now - prev.time

        self._cache[pid] = _ProcessCache(cpu_times=times, time=now)

        if delta_time <= 0:
            return 0.0

        return (delta_cpu / delta_time) * 100.0
