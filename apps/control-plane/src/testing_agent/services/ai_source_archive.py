from __future__ import annotations

import hashlib
import io
import posixpath
import stat
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from testing_agent.core.errors import (
    ErrBadRequest,
)
from testing_agent.core.sid import new_id
from testing_agent.models.ai_generate_task_source_archive import AiGenerateTaskSourceArchive
from testing_agent.repositories.ai_generate_task_source_archive import (
    AiGenerateTaskSourceArchiveRepository,
)
from testing_agent.services.ai_task_access import OwnedTask
from testing_agent.services.ai_task_output import dump_task

MAX_SOURCE_ARCHIVE_BYTES = 100 * 1024 * 1024


MAX_SOURCE_ARCHIVE_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024


MAX_SOURCE_ARCHIVE_FILES = 50_000


def _canonical_archive_path(name: str) -> str:
    normalized = name.replace("\\", "/")
    windows_path = PureWindowsPath(name)
    if (
        not normalized
        or "\x00" in normalized
        or PurePosixPath(normalized).is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
    ):
        raise ErrBadRequest
    parts = PurePosixPath(normalized).parts
    if any(part == ".." for part in parts):
        raise ErrBadRequest
    canonical = posixpath.normpath(normalized).rstrip("/")
    if canonical in {"", "."}:
        raise ErrBadRequest
    return canonical.casefold()


def validate_source_archive(filename: str, content: bytes) -> None:
    if Path(filename).suffix.casefold() != ".zip":
        raise ErrBadRequest
    if len(content) > MAX_SOURCE_ARCHIVE_BYTES:
        raise ErrBadRequest
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            paths: set[str] = set()
            file_count = 0
            total_size = 0
            for item in archive.infolist():
                canonical_path = _canonical_archive_path(item.filename)
                if canonical_path in paths:
                    raise ErrBadRequest
                paths.add(canonical_path)
                unix_mode = item.external_attr >> 16
                if stat.S_ISLNK(unix_mode):
                    raise ErrBadRequest
                if item.is_dir():
                    continue
                file_count += 1
                total_size += item.file_size
                if (
                    file_count > MAX_SOURCE_ARCHIVE_FILES
                    or total_size > MAX_SOURCE_ARCHIVE_UNCOMPRESSED_BYTES
                ):
                    raise ErrBadRequest
                with archive.open(item) as member:
                    while member.read(1024 * 1024):
                        pass
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, RuntimeError) as exc:
        raise ErrBadRequest from exc


class SourceArchiveManager:
    def __init__(
        self,
        *,
        source_archive_repository: AiGenerateTaskSourceArchiveRepository,
        source_archive_storage_root: Path,
        owned_task: OwnedTask,
        id_factory: Callable[[], str] = new_id,
    ):
        self.source_archive_repository = source_archive_repository
        self.source_archive_storage_root = source_archive_storage_root
        self.owned_task = owned_task
        self.new_id = id_factory

    async def upload_source_archive(
        self, task_id: str, filename: str, content: bytes, user_id: str
    ) -> dict[str, Any]:
        task = await self.owned_task(user_id, task_id, "ui", action="write")
        safe_filename = Path(filename).name
        validate_source_archive(safe_filename, content)

        archive_id = self.new_id()
        uploaded_at = datetime.now(UTC)
        task_storage_root = self.source_archive_storage_root / task.task_id
        target_path = task_storage_root / f"{archive_id}.zip"
        temporary_path = task_storage_root / f".{archive_id}.tmp"
        task_storage_root.mkdir(parents=True, exist_ok=True)
        temporary_path.write_bytes(content)
        temporary_path.replace(target_path)

        source_repository = self.source_archive_repository
        archive = await source_repository.get_source_archive_for_update(task.task_id)
        old_path = Path(archive.storage_path) if archive is not None else None
        if archive is None:
            archive = AiGenerateTaskSourceArchive(
                archive_id=archive_id,
                task_id=task.task_id,
                filename=safe_filename,
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                storage_path=str(target_path),
                uploaded_at=uploaded_at,
            )
            source_repository.add(archive)
        else:
            archive.archive_id = archive_id
            archive.filename = safe_filename
            archive.size_bytes = len(content)
            archive.sha256 = hashlib.sha256(content).hexdigest()
            archive.storage_path = str(target_path)
            archive.uploaded_at = uploaded_at

        try:
            await source_repository.commit()
        except Exception:
            target_path.unlink(missing_ok=True)
            if hasattr(source_repository, "rollback"):
                await source_repository.rollback()
            raise

        if old_path is not None and old_path != target_path:
            try:
                if old_path.resolve().is_relative_to(self.source_archive_storage_root.resolve()):
                    old_path.unlink(missing_ok=True)
            except OSError:
                pass
        return dump_task(task, archive)
