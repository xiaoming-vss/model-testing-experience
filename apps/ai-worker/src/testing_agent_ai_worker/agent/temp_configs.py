"""Track task-scoped credential files so shutdown can remove them immediately."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_ACTIVE: set[Path] = set()
_LOCK = threading.Lock()
# Both backends name their per-task credential file "<backend>-task-*.json".
TASK_CONFIG_PATTERNS = ("pi-task-*.json", "nanobot-task-*.json")


@contextmanager
def tracked(path: Path) -> Iterator[Path]:
    """Register a temporary config for the duration of one task call."""

    with _LOCK:
        _ACTIVE.add(path)
    try:
        yield path
    finally:
        with _LOCK:
            _ACTIVE.discard(path)
        Path(path).unlink(missing_ok=True)


def cleanup_task_configs() -> None:
    """Remove active credential files before immediate Worker shutdown."""

    with _LOCK:
        for path in tuple(_ACTIVE):
            Path(path).unlink(missing_ok=True)
        _ACTIVE.clear()


def sweep_task_configs(temp_configs_dir: Path) -> None:
    """Remove credential files left behind by a process killed before cleanup.

    SIGKILL and OOM never reach the task or signal cleanup, so the next start
    clears the previous run's plaintext configuration before claiming work.
    """

    with _LOCK:
        for pattern in TASK_CONFIG_PATTERNS:
            for path in Path(temp_configs_dir).glob(pattern):
                if path not in _ACTIVE:
                    path.unlink(missing_ok=True)
