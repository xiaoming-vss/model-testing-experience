"""Small secure file helpers for runtime artifacts."""

from __future__ import annotations

import os
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
    flags = os.O_WRONLY | os.O_CREAT
    flags |= os.O_TRUNC if overwrite else os.O_EXCL
    fd = os.open(path, flags, mode)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if fd >= 0:
            os.close(fd)
