"""Track task-scoped credential files so shutdown can remove them immediately."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_ACTIVE: set[Path] = set()
_LOCK = threading.Lock()


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
