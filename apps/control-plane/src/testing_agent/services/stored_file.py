"""File lifecycle and access. Business services attach inside their transaction."""

from __future__ import annotations

import asyncio
import mimetypes
from datetime import UTC, datetime, timedelta

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import AppError, ErrForbidden, ErrNotFound
from testing_agent.core.object_storage import ObjectStorage, ObjectStorageSettings
from testing_agent.core.sid import new_id
from testing_agent.models.project import Project
from testing_agent.models.project_skill_space import ProjectSkillSpace
from testing_agent.models.stored_file import StoredFile
from testing_agent.schemas.stored_file import FileUploadRequest
from testing_agent.services.project_access import require_project_id

ALLOWED_EXTENSIONS = {
    "txt",
    "md",
    "log",
    "json",
    "yaml",
    "yml",
    "csv",
    "png",
    "jpg",
    "jpeg",
    "pdf",
    "docx",
    "zip",
    "mp4",
}

# Business folders are assigned by the server, never supplied as upload paths.
PURPOSE_FOLDERS = {
    "requirement": "requirements",
    "attachment": "attachments",
    "ui_source_archive": "source-archives",
    "project_skill": "skills",
    "ui_artifact": "ui-artifacts",
}


def utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


class StoredFileService:
    def __init__(self, session: AsyncSession, settings: ObjectStorageSettings, storage=None):
        self.session = session
        self.settings = settings
        self._storage = storage

    @property
    def storage(self):
        if not self.settings.enabled:
            raise AppError(503, "S3 文件存储未启用", 503)
        if self._storage is None:
            self._storage = ObjectStorage(self.settings)
        return self._storage

    async def get(self, file_id: str, *, lock=False):
        query = select(StoredFile).where(StoredFile.file_id == file_id)
        if lock:
            query = query.with_for_update()
        row = await self.session.scalar(query.execution_options(populate_existing=True))
        if row is None:
            raise ErrNotFound
        if row.bucket != self.settings.bucket:
            raise AppError(503, "文件存储配置与记录不一致", 503)
        return row

    async def initiate(
        self, user_id: str, body: FileUploadRequest, *, resource_type="", resource_id=""
    ):
        await require_project_id(self.session, user_id, body.project_id, "write")
        ext = body.filename.rsplit(".", 1)[-1].lower()
        allowed = {"txt", "md", "docx"} if body.purpose == "requirement" else ALLOWED_EXTENSIONS
        maximum = self.settings.max_bytes
        if body.purpose == "ui_source_archive":
            from testing_agent.services.ai_source_archive import MAX_SOURCE_ARCHIVE_BYTES

            allowed = {"zip"}
            maximum = min(maximum, MAX_SOURCE_ARCHIVE_BYTES)
        if body.purpose == "project_skill":
            allowed = None
            await require_project_id(self.session, user_id, body.project_id, "manage")
        if body.purpose == "ui_artifact":
            allowed = {"png", "zip", "mp4", "webm"}
        if (allowed is not None and ext not in allowed) or body.size > maximum:
            raise AppError(400, "文件类型不支持或超过大小限制", 400)
        file_id = new_id()
        prefix = "/".join(
            part
            for part in (
                self.settings.prefix.strip("/"),
                body.project_id,
                PURPOSE_FOLDERS[body.purpose],
                file_id,
            )
            if part
        )
        if body.purpose == "project_skill":
            prefix = "/".join(
                filter(
                    None,
                    [
                        self.settings.prefix.strip("/"),
                        "_temporary",
                        "skills",
                        body.project_id,
                        file_id,
                    ],
                )
            )
        row = StoredFile(
            file_id=file_id,
            project_id=body.project_id,
            uploaded_by=user_id,
            filename=body.filename,
            size=body.size,
            sha256=body.sha256,
            content_type=mimetypes.guess_type(body.filename)[0] or "application/octet-stream",
            bucket=self.settings.bucket,
            object_key=prefix + "/" + body.filename,
            staging_key=prefix + "/upload",
            purpose=body.purpose,
            status="pending",
            resource_type=resource_type,
            resource_id=resource_id,
            expires_at=utcnow() + timedelta(hours=self.settings.temporary_hours),
        )
        ticket = await asyncio.to_thread(self.storage.upload_ticket, row.staging_key, row.size)
        self.session.add(row)
        await self.session.commit()
        return {"fileId": file_id, "upload": ticket, "expiresIn": self.settings.signature_seconds}

    async def complete(self, user_id: str, file_id: str):
        row = await self.get(file_id, lock=True)
        await require_project_id(self.session, user_id, row.project_id, "write")
        if row.uploaded_by != user_id:
            raise ErrForbidden
        if row.status in {"ready", "attached"}:
            return {"fileId": file_id, "status": row.status}
        if row.status != "pending" or row.expires_at <= utcnow():
            raise AppError(409, "上传已过期，请重新上传", 409)
        validator = None
        if row.purpose == "ui_source_archive":
            from functools import partial

            from testing_agent.services.ai_source_archive import validate_source_archive

            validator = partial(validate_source_archive, row.filename)
        try:
            await asyncio.to_thread(
                self.storage.seal,
                row.staging_key,
                row.object_key,
                row.size,
                row.sha256,
                row.filename,
                validator=validator,
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                raise AppError(409, "文件尚未上传完成，请重新上传", 409) from None
            raise AppError(503, "对象存储核验失败，请检查配置后重试", 503) from None
        except BotoCoreError:
            raise AppError(503, "对象存储暂不可用，请重试", 503) from None
        row.status = "ready"
        row.completed_at = utcnow()
        await self.session.commit()
        return {"fileId": file_id, "status": "ready"}

    async def attach(
        self,
        user_id: str,
        file_id: str,
        project_id: str,
        resource_type: str,
        resource_id: str,
        *,
        purpose: str,
    ):
        row = await self.get(file_id, lock=True)
        await require_project_id(self.session, user_id, project_id, "write")
        if row.project_id != project_id or row.uploaded_by != user_id:
            raise ErrForbidden
        if row.purpose != purpose:
            raise AppError(409, "文件用途不匹配", 409)
        if row.status == "attached" and (row.resource_type, row.resource_id) == (
            resource_type,
            resource_id,
        ):
            return row
        if row.status != "ready" or row.purpose != purpose or row.expires_at <= utcnow():
            raise AppError(409, "文件未完成上传或不可关联", 409)
        row.status, row.resource_type, row.resource_id = "attached", resource_type, resource_id
        return row

    async def ticket(self, row: StoredFile):
        if row.status not in {"ready", "attached"}:
            raise ErrNotFound
        if row.status == "ready" and row.expires_at <= utcnow():
            raise ErrNotFound
        url = await asyncio.to_thread(self.storage.download_ticket, row.object_key, row.filename)
        return {
            "url": url,
            "size": row.size,
            "sha256": row.sha256,
            "filename": row.filename,
            "expiresIn": self.settings.signature_seconds,
        }

    async def accessible(self, user_id: str, file_id: str):
        row = await self.get(file_id)
        await require_project_id(self.session, user_id, row.project_id)
        if row.status != "attached" and row.uploaded_by != user_id:
            raise ErrForbidden
        if row.status == "deleting":
            raise ErrNotFound
        return row

    async def list_by_resource(
        self, project_id: str, resource_type: str, resource_id: str
    ) -> list[StoredFile]:
        """列出业务资源已关联的文件，供详情响应组装附件区。"""
        return list(
            (
                await self.session.scalars(
                    select(StoredFile)
                    .where(
                        StoredFile.project_id == project_id,
                        StoredFile.resource_type == resource_type,
                        StoredFile.resource_id == resource_id,
                        StoredFile.status == "attached",
                    )
                    .order_by(StoredFile.id)
                )
            ).all()
        )

    async def metadata(self, user_id: str, file_id: str):
        row = await self.accessible(user_id, file_id)
        return {
            "fileId": row.file_id,
            "projectId": row.project_id,
            "filename": row.filename,
            "contentType": row.content_type,
            "size": row.size,
            "sha256": row.sha256,
            "status": row.status,
            "uploadedBy": row.uploaded_by,
            "createdAt": row.created_at,
            "completedAt": row.completed_at,
        }

    async def download(self, user_id: str, file_id: str):
        return await self.ticket(await self.accessible(user_id, file_id))

    async def cleanup(self):
        # Claim expired rows while holding the same lock used by complete/attach.
        rows = list(
            (
                await self.session.scalars(
                    select(StoredFile)
                    .where(
                        StoredFile.expires_at < utcnow(),
                        StoredFile.status.in_(["pending", "ready", "deleting"]),
                    )
                    .with_for_update(skip_locked=True)
                    .limit(100)
                )
            ).all()
        )
        for row in rows:
            row.status = "deleting"
        await self.session.commit()
        deleted, failed = 0, 0
        identifiers = [row.file_id for row in rows]
        for file_id in identifiers:
            try:
                row = await self.get(file_id)
                # Readable skill paths are reused. Serialize with publication and
                # never let an old file record delete a currently attached object.
                if row.purpose == "project_skill":
                    if row.project_id:
                        await self.session.scalar(
                            select(Project)
                            .where(Project.project_id == row.project_id)
                            .with_for_update()
                        )
                    else:
                        await self.session.scalar(
                            select(ProjectSkillSpace)
                            .where(ProjectSkillSpace.skill_space_id == row.resource_id)
                            .with_for_update()
                        )
                live = await self.session.scalar(
                    select(StoredFile.file_id)
                    .where(
                        StoredFile.bucket == row.bucket,
                        StoredFile.object_key == row.object_key,
                        StoredFile.file_id != row.file_id,
                        StoredFile.status.in_(["attached", "ready", "pending"]),
                    )
                    .with_for_update()
                    .limit(1)
                )
                if row.staging_key:
                    await asyncio.to_thread(self.storage.delete, row.staging_key)
                if live is None:
                    await asyncio.to_thread(self.storage.delete, row.object_key)
                await self.session.delete(row)
                await self.session.commit()
                deleted += 1
            except Exception:
                await self.session.rollback()
                failed += 1
        # Staging uploads can be replayed until expiry; only remove after the full temporary window.
        attached = list(
            (
                await self.session.scalars(
                    select(StoredFile)
                    .where(
                        StoredFile.expires_at < utcnow(),
                        StoredFile.status == "attached",
                        StoredFile.staging_key != "",
                    )
                    .limit(100)
                )
            ).all()
        )
        identifiers = [row.file_id for row in attached]
        for file_id in identifiers:
            try:
                row = await self.get(file_id)
                if row.staging_key:
                    await asyncio.to_thread(self.storage.delete, row.staging_key)
                row.staging_key = ""
                await self.session.commit()
            except Exception:
                await self.session.rollback()
                failed += 1
        return {"deleted": deleted, "failed": failed}
