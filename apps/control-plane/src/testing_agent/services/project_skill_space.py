from __future__ import annotations

import asyncio
import hashlib
import io
import json
import zipfile
from datetime import timedelta

from sqlalchemy import select

from testing_agent.core.errors import AppError, ErrForbidden, ErrNotFound
from testing_agent.core.sid import new_id
from testing_agent.models.project import Project
from testing_agent.models.project_skill_space import ProjectSkillSpace
from testing_agent.models.stored_file import StoredFile
from testing_agent.services.common import list_payload
from testing_agent.services.project_access import require_project_access
from testing_agent.services.resource_deletion import ResourceDeletion, SqlResourceDeletion
from testing_agent.services.skill_storage import publish_skill_files
from testing_agent.services.stored_file import utcnow


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


async def replace_manifest(session, skill, manifest, signature_seconds):
    """Publish a complete file set in one transaction; old objects enter normal GC."""
    keep = {entry["fileId"] for entry in manifest}
    old = {entry["fileId"] for entry in (skill.manifest or [])} - keep
    if old:
        rows = await session.scalars(select(StoredFile).where(StoredFile.file_id.in_(old)))
        for row in rows:
            if row.resource_type == "project_skill" and row.resource_id == skill.skill_space_id:
                row.status = "deleting"
                row.expires_at = utcnow() + timedelta(seconds=signature_seconds)
    skill.manifest = sorted(manifest, key=lambda entry: entry["path"])
    skill.hash = hashlib.sha256(json.dumps(skill.manifest, sort_keys=True).encode()).hexdigest()
    skill.size_bytes = sum(entry["size"] for entry in manifest)
    skill.updated_at = utcnow()


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

    async def upload(self, project_id, body, user_id):
        await self.ensure_project_access(user_id, project_id, action="manage")
        if self.files is None:
            raise AppError(503, "S3 文件存储未启用", 503)
        session = self.repository.session
        # Serialize replacements of the same project's skill file sets.
        await session.scalar(
            select(Project).where(Project.project_id == project_id).with_for_update()
        )
        default = await session.scalar(
            select(ProjectSkillSpace).where(
                ProjectSkillSpace.is_default.is_(True), ProjectSkillSpace.filename == body.name
            )
        )
        if default:
            raise AppError(409, "不能上传与系统默认 Skill 同名的技能", 409)
        skill = await self.repository.get_active_by_project_and_filename(project_id, body.name)
        if skill is None:
            skill = ProjectSkillSpace(
                skill_space_id=new_id(),
                project_id=project_id,
                scope_key=project_id,
                filename=body.name,
                is_default=False,
                manifest=[],
                hash="",
                size_bytes=0,
            )
            self.repository.add(skill)
        elif skill.is_default:
            raise ErrForbidden()
        manifest = []
        old_paths = {entry["fileId"]: entry["path"] for entry in skill.manifest}
        for entry in body.files:
            if entry.file_id in old_paths and old_paths[entry.file_id] != entry.path:
                raise AppError(400, "更改技能文件路径需要重新上传文件", 400)
            row = await self.files.attach(
                user_id,
                entry.file_id,
                project_id,
                "project_skill",
                skill.skill_space_id,
                purpose="project_skill",
            )
            if row.filename != entry.path.rsplit("/", 1)[-1]:
                raise AppError(400, "技能文件名与上传文件不一致", 400)
            manifest.append(
                {"path": entry.path, "fileId": row.file_id, "size": row.size, "sha256": row.sha256}
            )
        if sum(entry["size"] for entry in manifest) > self.files.settings.max_bytes:
            raise AppError(400, "技能文件夹超过大小限制", 400)
        async with publish_skill_files(self.files, skill, manifest):
            await replace_manifest(session, skill, manifest, self.files.settings.signature_seconds)
            await self.repository.commit()
        await self.repository.refresh(skill)
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
