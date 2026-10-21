from __future__ import annotations

import asyncio
import hashlib
import io
import zipfile
from typing import Any

from sqlalchemy import select

from testing_agent.core.errors import AppError, ErrNotFound
from testing_agent.models.project import Project
from testing_agent.schemas.project_skill_space import ProjectSkillUploadRequest
from testing_agent.services.common import list_payload
from testing_agent.services.project_access import require_project_access
from testing_agent.services.resource_deletion import ResourceDeletion, SqlResourceDeletion
from testing_agent.services.skill_storage import SkillPublisher, replace_manifest


def dump_skill(skill):
    return {
        "skillSpaceId": skill.skill_space_id,
        "projectId": skill.project_id,
        "filename": skill.filename,
        "hash": skill.hash,
        "size": skill.size_bytes,
        "fileCount": len(skill.manifest),
        "isDefault": skill.is_default,
        "createdAt": skill.created_at,
        "updatedAt": skill.updated_at,
    }


class ProjectSkillSpaceService:
    def __init__(self, repository, files=None, *, deletion: ResourceDeletion | None = None) -> None:
        self.deletion = deletion or SqlResourceDeletion()
        self.repository, self.files = repository, files

    async def ensure_project_access(self, user_id, project_id, *, action="read"):
        project = await self.repository.get_project(project_id)
        if project is None:
            raise ErrNotFound()
        await require_project_access(self.repository.session, user_id, project, action)

    async def list(self, project_id, user_id):
        await self.ensure_project_access(user_id, project_id)
        return list_payload([dump_skill(row) for row in await self.repository.list(project_id)])

    async def upload(
        self, project_id: str, body: ProjectSkillUploadRequest, user_id: str
    ) -> dict[str, Any]:
        if self.files is None:
            raise AppError(503, "S3 文件存储未启用", 503)
        skill = await SkillPublisher(self.files).project(project_id, body, user_id)
        return dump_skill(skill)

    async def delete(self, project_id, skill_space_id, user_id):
        await self.ensure_project_access(user_id, project_id, action="manage")
        await self.repository.session.scalar(
            select(Project).where(Project.project_id == project_id).with_for_update()
        )
        skill = await self.repository.get(project_id, skill_space_id)
        if skill is None:
            raise ErrNotFound()
        if skill.is_default:
            raise AppError(403, "系统默认 Skill 不允许删除", 403)
        await replace_manifest(
            self.repository.session, skill, [], self.files.settings.signature_seconds
        )
        await self.deletion.delete(self.repository.session, skill)
        await self.repository.commit()
        return {}

    async def download_zip(self, project_id, skill_space_id, user_id):
        await self.ensure_project_access(user_id, project_id)
        skill = await self.repository.get(project_id, skill_space_id)
        if skill is None:
            raise ErrNotFound()
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for entry in skill.manifest:
                row = await self.files.get(entry["fileId"])
                content = await asyncio.to_thread(self._read_file, row)
                archive.writestr(skill.filename + "/" + entry["path"], content)
        return skill.filename + ".zip", output.getvalue()

    def _read_file(self, row):
        storage = self.files.storage
        obj = storage.client.get_object(Bucket=row.bucket, Key=row.object_key)
        try:
            content = obj["Body"].read(row.size + 1)
        finally:
            obj["Body"].close()
        if len(content) != row.size or hashlib.sha256(content).hexdigest() != row.sha256:
            raise AppError(409, "技能文件校验失败", 409)
        return content
