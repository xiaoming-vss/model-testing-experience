"""Short transactions around private, generation-specific storage verification."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import AppError, ErrForbidden, ErrNotFound
from testing_agent.core.http_diagnostics import safe_exception_trace
from testing_agent.core.object_storage import ObjectStorage, ObjectStorageSettings
from testing_agent.core.sid import new_id
from testing_agent.domain.project_policy import allows_project_action, effective_project_role
from testing_agent.models.file_verification import FileVerification
from testing_agent.models.stored_file import StoredFile
from testing_agent.repositories.file_verification import FileVerificationRepository

logger = logging.getLogger(__name__)
VERIFY_WINDOW = timedelta(minutes=10)
GC_INTERVAL = timedelta(minutes=5)


def now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True)
class VerificationInput:
    file_id: str
    project_id: str
    uploaded_by: str
    bucket: str
    staging_key: str
    size: int
    sha256: str
    filename: str
    purpose: str

    @classmethod
    def from_row(cls, row: StoredFile) -> VerificationInput:
        return cls(**{name: getattr(row, name) for name in cls.__dataclass_fields__})


class FileVerificationWorkflow:
    """Owns complete's commits; never use inside an uncommitted business mutation."""

    def __init__(
        self, session: AsyncSession, settings: ObjectStorageSettings, storage: ObjectStorage
    ):
        self.session, self.settings, self.storage = session, settings, storage
        self.repository = FileVerificationRepository(session)

    async def authorized(self, project_id: str, actor: str) -> None:
        project, user, role = await self.repository.access_facts(project_id, actor)
        if project is None:
            raise ErrNotFound()
        if user is None or user.status != "active":
            raise ErrForbidden()
        effective = effective_project_role(
            is_owner=project.user_id == actor,
            member_role=role,
            is_super_admin=user.is_super_admin,
        )
        if not allows_project_action(effective, "write"):
            raise ErrForbidden()

    async def complete(self, actor: str, file_id: str) -> dict[str, str]:
        try:
            row = await self.repository.file(file_id)
            if row is None:
                raise ErrNotFound()
            project_id = row.project_id
            await self.authorized(project_id, actor)
            row = await self.repository.file(file_id, lock=True)
            if row is None:
                raise ErrNotFound()
            if row.project_id != project_id or row.uploaded_by != actor:
                raise ErrForbidden()
            if row.bucket != self.settings.bucket:
                raise AppError(503, "文件存储配置与记录不一致", 503)
            if row.status in {"ready", "attached", "archived"}:
                status = row.status
                await self.session.commit()
                return {"fileId": file_id, "status": status}
            now = now_utc()
            if row.status != "pending" or row.expires_at <= now:
                raise AppError(409, "上传已过期，请重新上传", 409)
            previous = (
                await self.repository.operation(row.verification_id)
                if row.verification_id
                else None
            )
            if previous is not None and previous.state == "running":
                if previous.deadline > now:
                    raise AppError(409, "文件正在核验，请稍后查询或重试", 409)
                previous.state = "abandoned"
            operation_id = new_id()
            source = VerificationInput.from_row(row)
            key = "/".join(
                [row.staging_key.rsplit("/", 1)[0], "verified", operation_id, row.filename]
            )
            if len(key) > 512 or len(key.encode()) > 1024:
                raise AppError(400, "文件存储路径过长，请缩短文件名", 400)
            operation: FileVerification | None = FileVerification(
                operation_id=operation_id,
                file_id=file_id,
                bucket=row.bucket,
                object_key=key,
                state="running",
                deadline=now + VERIFY_WINDOW,
                gc_after=now + VERIFY_WINDOW,
            )
            row.verification_id = operation_id
            self.session.add(operation)
            await self.session.commit()
        except BaseException:
            await self.session.rollback()
            raise

        # The thread sees only frozen values. Cancellation cannot publish or reuse its key.
        try:
            size, sha256 = await asyncio.to_thread(self.verify, source, key)
        except asyncio.CancelledError:
            # A cancelled to_thread may still write. Durable running record is intentionally
            # retained; after its deadline it is fenced and repeatedly garbage-collected.
            raise
        except Exception as exc:
            await self.discard(file_id, operation_id)
            if isinstance(exc, ClientError):
                if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                    raise AppError(409, "文件尚未上传完成，请重新上传", 409) from None
                raise AppError(503, "对象存储核验失败，请检查配置后重试", 503) from None
            if isinstance(exc, BotoCoreError):
                raise AppError(503, "对象存储暂不可用，请重试", 503) from None
            raise
        try:
            await self.authorized(source.project_id, actor)
            row = await self.repository.file(file_id, lock=True)
            operation = await self.repository.operation(operation_id)
            now = now_utc()
            if (
                row is None
                or operation is None
                or row.status != "pending"
                or row.verification_id != operation_id
                or operation.state != "running"
                or operation.deadline <= now
                or row.expires_at <= now
                or VerificationInput.from_row(row) != source
            ):
                raise AppError(409, "文件核验已失效，请重新确认上传状态", 409)
            row.object_key, row.size, row.sha256 = key, size, sha256
            row.status, row.completed_at = "ready", now
            operation.state, operation.settled_at = "published", now
            await self.session.commit()
        except BaseException:
            await self.session.rollback()
            # Storage has returned; a rejected publication can now be reclaimed once.
            await self.discard(file_id, operation_id)
            raise
        return {"fileId": file_id, "status": "ready"}

    def verify(self, source: VerificationInput, key: str) -> tuple[int, str]:
        validator = None
        if source.purpose == "ui_source_archive":
            from testing_agent.services.ai_source_archive import validate_source_archive

            validator = partial(validate_source_archive, source.filename)
        self.storage.seal(
            source.staging_key,
            key,
            source.size,
            source.sha256,
            source.filename,
            validator=validator,
        )
        if source.purpose == "requirement" and source.filename.lower().endswith(".html"):
            from testing_agent.domain.rich_text import has_rich_text_content, sanitize_rich_text

            clean = sanitize_rich_text(self.storage.read_text(key))
            if not has_rich_text_content(clean):
                raise AppError(400, "请输入需求正文", 400)
            data = clean.encode("utf-8")
            self.storage.write_html(key, data, source.filename)
            return len(data), hashlib.sha256(data).hexdigest()
        return source.size, source.sha256

    async def discard(self, file_id: str, operation_id: str) -> None:
        try:
            row = await self.repository.file(file_id, lock=True)
            operation = await self.repository.operation(operation_id)
            if operation is not None and operation.state != "published":
                operation.state, operation.settled_at = "discarded", now_utc()
                operation.gc_after = now_utc()
                if row is not None and row.verification_id == operation_id:
                    row.verification_id = ""
            await self.session.commit()
        except BaseException:
            await self.session.rollback()
            raise

    async def collect(self, limit: int = 100) -> dict[str, int]:
        """Never drop an unsettled tombstone: its old thread may still write after delete."""
        now = now_utc()
        rows = await self.repository.garbage(self.settings.bucket, now, limit)
        claimed: list[tuple[str, str]] = []
        for row in rows:
            if row.state == "running":
                row.state = "abandoned"
            row.gc_after = now + GC_INTERVAL
            claimed.append((row.operation_id, row.object_key))
        await self.session.commit()
        deleted, failed = 0, 0
        for operation_id, key in claimed:
            try:
                await asyncio.to_thread(self.storage.delete, key)
                current = await self.repository.operation(operation_id)
                if (
                    current is not None
                    and current.state == "discarded"
                    and current.settled_at is not None
                ):
                    await self.session.delete(current)
                await self.session.commit()
                deleted += 1
            except Exception as exc:
                await self.session.rollback()
                failed += 1
                logger.warning(
                    "File verification cleanup failed operation_id=%s error=%s trace=%s",
                    operation_id,
                    type(exc).__name__,
                    safe_exception_trace(exc),
                )
        return {"deleted": deleted, "failed": failed}
