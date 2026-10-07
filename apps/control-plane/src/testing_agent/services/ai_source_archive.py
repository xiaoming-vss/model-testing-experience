from __future__ import annotations

import io
import posixpath
import stat
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, BinaryIO

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
        raise ErrBadRequest()
    parts = PurePosixPath(normalized).parts
    if any(part == ".." for part in parts):
        raise ErrBadRequest()
    canonical = posixpath.normpath(normalized).rstrip("/")
    if canonical in {"", "."}:
        raise ErrBadRequest()
    return canonical.casefold()


def validate_source_archive(filename: str, content: bytes | BinaryIO) -> None:
    if Path(filename).suffix.casefold() != ".zip":
        raise ErrBadRequest()
    stream = io.BytesIO(content) if isinstance(content, (bytes, bytearray)) else content
    size = stream.seek(0, 2)
    stream.seek(0)
    if size > MAX_SOURCE_ARCHIVE_BYTES:
        raise ErrBadRequest()
    try:
        with zipfile.ZipFile(stream) as archive:
            paths: set[str] = set()
            file_count = 0
            total_size = 0
            for item in archive.infolist():
                canonical_path = _canonical_archive_path(item.filename)
                if canonical_path in paths:
                    raise ErrBadRequest()
                paths.add(canonical_path)
                unix_mode = item.external_attr >> 16
                if stat.S_ISLNK(unix_mode):
                    raise ErrBadRequest()
                if item.is_dir():
                    continue
                file_count += 1
                total_size += item.file_size
                if (
                    file_count > MAX_SOURCE_ARCHIVE_FILES
                    or total_size > MAX_SOURCE_ARCHIVE_UNCOMPRESSED_BYTES
                ):
                    raise ErrBadRequest()
                with archive.open(item) as member:
                    while member.read(1024 * 1024):
                        pass
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, RuntimeError) as exc:
        raise ErrBadRequest() from exc


class SourceArchiveManager:
    def __init__(
        self,
        *,
        source_archive_repository: AiGenerateTaskSourceArchiveRepository,
        files,
        owned_task: OwnedTask,
        id_factory: Callable[[], str] = new_id,
    ):
        self.source_archive_repository = source_archive_repository
        self.files = files
        self.owned_task = owned_task
        self.new_id = id_factory

    async def upload_source_archive(
        self, task_id: str, file_id: str, user_id: str
    ) -> dict[str, Any]:
        task = await self.owned_task(user_id, task_id, "ui", action="write")
        if self.files is None:
            raise ErrBadRequest()
        source_repository = self.source_archive_repository
        try:
            row = await self.files.attach(
                user_id,
                file_id,
                task.project_id,
                "ui_source_archive",
                task.task_id,
                purpose="ui_source_archive",
            )
            archive = await source_repository.get_source_archive_for_update(task.task_id)
            if archive is not None and archive.file_id == row.file_id:
                return dump_task(task, archive)
            if archive is None:
                archive = AiGenerateTaskSourceArchive(task_id=task.task_id)
                source_repository.add(archive)
            archive.archive_id = self.new_id()
            archive.file_id = row.file_id
            archive.filename = row.filename
            archive.size_bytes = row.size
            archive.sha256 = row.sha256
            archive.storage_path = ""
            archive.uploaded_at = datetime.now(UTC)
            await source_repository.commit()
        except Exception:
            await source_repository.rollback()
            raise
        return dump_task(task, archive)
