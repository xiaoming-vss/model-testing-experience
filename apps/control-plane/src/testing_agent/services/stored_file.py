"""File lifecycle and access. Business services attach inside their transaction."""

from __future__ import annotations

import asyncio
import mimetypes
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import AppError, ErrForbidden, ErrNotFound
from testing_agent.core.object_storage import ObjectStorage, ObjectStorageSettings
from testing_agent.core.sid import new_id
from testing_agent.models.stored_file import StoredFile
from testing_agent.schemas.stored_file import FileUploadRequest
from testing_agent.services.project_access import ProjectAction, require_project_id
from testing_agent.services.stored_file_access import require_file_resource

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

# 禅道拉取在浏览器允许集之上放宽常见截图/压缩格式；svg 因脚本风险始终排除。
PULL_EXTENSIONS = ALLOWED_EXTENSIONS | {"gif", "bmp", "webm", "7z", "gz"}

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
            raise ErrNotFound()
        if row.bucket != self.settings.bucket:
            raise AppError(503, "文件存储配置与记录不一致", 503)
        return row

    async def initiate(
        self, user_id: str, body: FileUploadRequest, *, resource_type="", resource_id=""
    ):
        await require_project_id(self.session, user_id, body.project_id, "write")
        ext = body.filename.rsplit(".", 1)[-1].lower()
        allowed: set[str] | None = (
            {"txt", "md", "docx", "html"} if body.purpose == "requirement" else ALLOWED_EXTENSIONS
        )
        maximum = self.settings.max_bytes
        if body.purpose == "requirement" and ext == "html":
            maximum = min(maximum, 1024 * 1024)
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

    async def initiate_pull(
        self,
        user_id: str,
        project_id: str,
        *,
        bug_id: str,
        filename: str,
        size: int,
        sha256: str,
    ):
        """禅道反向拉取的内部上传票据：调用方是项目 MCP，而非浏览器（R44/R46）。

        大小与摘要来自远端元数据核对，MCP 上传后由 complete 的 seal 再校验一次。
        """
        await require_project_id(self.session, user_id, project_id, "write")
        filename = (filename or "").strip() or "attachment"
        filename = filename.replace("\\", "_").replace("/", "_")
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if size <= 0 or size > self.settings.max_bytes:
            raise AppError(400, "远端文件大小超出平台限制", 400)
        if ext and ext not in PULL_EXTENSIONS:
            raise AppError(400, f"远端文件类型 .{ext} 不支持导入", 400)
        file_id = new_id()
        prefix = "/".join(
            part
            for part in (
                self.settings.prefix.strip("/"),
                project_id,
                PURPOSE_FOLDERS["attachment"],
                file_id,
            )
            if part
        )
        row = StoredFile(
            file_id=file_id,
            project_id=project_id,
            uploaded_by=user_id,
            filename=filename,
            size=size,
            sha256=sha256,
            content_type=mimetypes.guess_type(filename)[0] or "application/octet-stream",
            bucket=self.settings.bucket,
            object_key=prefix + "/" + filename,
            staging_key=prefix + "/upload",
            purpose="attachment",
            status="pending",
            resource_type="bug",
            resource_id=bug_id,
            expires_at=utcnow() + timedelta(hours=self.settings.temporary_hours),
        )
        ticket = await asyncio.to_thread(self.storage.upload_put_ticket, row.staging_key)
        self.session.add(row)
        await self.session.commit()
        return {"fileId": file_id, "upload": ticket, "expiresIn": self.settings.signature_seconds}

    async def complete(self, user_id: str, file_id: str) -> dict[str, str]:
        from testing_agent.services.file_verification import FileVerificationWorkflow

        return await FileVerificationWorkflow(self.session, self.settings, self.storage).complete(
            user_id, file_id
        )

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
        if row.project_id != project_id:
            raise ErrForbidden()
        if row.purpose != purpose:
            raise AppError(409, "文件用途不匹配", 409)
        if row.status in {"attached", "archived"} and (row.resource_type, row.resource_id) == (
            resource_type,
            resource_id,
        ):
            row.status = "attached"
            return row
        if row.uploaded_by != user_id:
            raise ErrForbidden()
        if row.status != "ready" or row.purpose != purpose or row.expires_at <= utcnow():
            raise AppError(409, "文件未完成上传或不可关联", 409)
        row.status, row.resource_type, row.resource_id = "attached", resource_type, resource_id
        return row

    async def ticket(self, row: StoredFile):
        if row.status not in {"ready", "attached", "archived"}:
            raise ErrNotFound()
        if row.status == "ready" and row.expires_at <= utcnow():
            raise ErrNotFound()
        await require_file_resource(self.session, row)
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
        action: ProjectAction = (
            "bug_read"
            if row.status in {"attached", "archived"} and row.resource_type == "bug"
            else "read"
        )
        await require_project_id(self.session, user_id, row.project_id, action)
        if row.status not in {"attached", "archived"} and row.uploaded_by != user_id:
            raise ErrForbidden()
        if row.status == "deleting":
            raise ErrNotFound()
        await require_file_resource(self.session, row)
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

    async def cleanup(self) -> dict[str, int]:
        from testing_agent.services.stored_file_cleanup import StoredFileCleanup

        return await StoredFileCleanup(self.session, self.settings, self.storage).cleanup()
