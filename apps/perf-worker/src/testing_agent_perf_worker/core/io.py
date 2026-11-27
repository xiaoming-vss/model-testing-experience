"""Small secure file helpers for runtime artifacts."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def mkdir_secure(path: Path, mode: int = 0o700) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=mode)
    os.chmod(path, mode)


def write_secure_text(path: Path, text: str, *, overwrite: bool = False, mode: int = 0o600) -> None:
    _write_secure(path, text.encode("utf-8"), overwrite=overwrite, mode=mode)


def write_secure_bytes(
    path: Path, data: bytes, *, overwrite: bool = False, mode: int = 0o600
) -> None:
    _write_secure(path, data, overwrite=overwrite, mode=mode)


def _write_secure(path: Path, data: bytes, *, overwrite: bool, mode: int) -> None:
    mkdir_secure(path.parent)
    if overwrite:
        # A reader such as the container probe must never see a half-written file.
        descriptor, name = tempfile.mkstemp(prefix=f"{path.name}.", dir=path.parent)
        try:
            _write_fd(descriptor, data, mode)
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    _write_fd(os.open(path, flags, mode), data, mode)


def _write_fd(fd: int, data: bytes, mode: int) -> None:
    """Write ``data`` and close ``fd``; the caller no longer owns the descriptor."""
    owned = True
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            owned = False  # the stream closes the descriptor
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if owned:
            os.close(fd)
