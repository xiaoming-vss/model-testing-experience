from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from testing_agent.core.errors import ErrNotFound, ErrProjectSkillSpaceFileInvalid
from testing_agent.core.sid import new_id
from testing_agent.models.project_skill_space import ProjectSkillSpace
from testing_agent.repositories.project_skill_space import ProjectSkillSpaceRepository
from testing_agent.services.common import list_payload
from testing_agent.services.project_access import ProjectAction, require_project_access


def dump_skill(skill: ProjectSkillSpace) -> dict[str, Any]:
    return {
        "skillSpaceId": skill.skill_space_id,
        "projectId": skill.project_id,
        "version": skill.version,
        "hash": skill.hash,
        "downloadUrl": skill.download_url,
        "filename": skill.filename,
        "size": skill.size_bytes,
        "isDefault": skill.is_default,
        "createdAt": skill.created_at,
        "updatedAt": skill.updated_at,
    }


def skill_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class ProjectSkillSpaceService:
    def __init__(self, repository: ProjectSkillSpaceRepository):
        self.repository = repository

    async def ensure_project_access(
        self, user_id: str, project_id: str, *, action: ProjectAction = "read"
    ) -> None:
        project = await self.repository.get_project(project_id)
        if project is None:
            raise ErrNotFound
        await require_project_access(self.repository.session, user_id, project, action)

    async def list(self, project_id: str, user_id: str) -> dict[str, Any]:
        await self.ensure_project_access(user_id, project_id, action="read")
        rows = await self.repository.list(project_id)
        return list_payload([dump_skill(row) for row in rows])

    async def create(self, project_id: str, body: dict[str, Any] | None, user_id: str) -> dict:
        await self.ensure_project_access(user_id, project_id, action="manage")
        data = body or {}
        filename = str(data.get("filename") or "skills.zip")
        content = str(data.get("content") or "").encode()
        return await self.upload(
            project_id,
            filename,
            content or filename.encode(),
            "",
            user_id,
            size=int(data.get("size", len(content))),
            storage_path=data.get("storagePath") or data.get("storage_path"),
            is_default=bool(data.get("isDefault", False)),
        )

    async def upload(
        self,
        project_id: str,
        filename: str,
        content: bytes,
        public_base_url: str,
        user_id: str,
        *,
        size: int | None = None,
        storage_path: str | None = None,
        is_default: bool = False,
    ) -> dict:
        await self.ensure_project_access(user_id, project_id, action="manage")
        if not filename.endswith((".zip", ".tar")):
            raise ErrProjectSkillSpaceFileInvalid
        digest = skill_hash(content)
        existing = None
        if hasattr(self.repository, "get_active_by_project_and_filename"):
            existing = await self.repository.get_active_by_project_and_filename(
                project_id,
                filename,
            )
        skill_space_id = new_id()
        if existing is not None:
            skill = existing
            skill.version = int(getattr(skill, "version", 0) or 0) + 1
            skill_space_id = skill.skill_space_id
        else:
            skill = ProjectSkillSpace(
                skill_space_id=skill_space_id,
                project_id=project_id,
                version=1,
            )
        final_storage_path = str(
            storage_path or f"storage/skills/{project_id}/{skill_space_id}/{filename}"
        )
        skill.hash = digest
        skill.download_url = (
            f"{public_base_url.rstrip('/')}/v1/projects/{project_id}/skills/{skill_space_id}/download"
            if public_base_url
            else f"/v1/projects/{project_id}/skills/{skill_space_id}/download"
        )
        skill.filename = filename
        skill.size_bytes = int(size if size is not None else len(content))
        skill.storage_path = final_storage_path
        skill.is_default = is_default if existing is None else False
        if getattr(self.repository, "writes_files", False):
            path = Path(final_storage_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        if existing is None:
            self.repository.add(skill)
        await self.repository.commit()
        await self.repository.refresh(skill)
        return dump_skill(skill)

    async def delete(self, project_id: str, skill_space_id: str, user_id: str) -> dict:
        await self.ensure_project_access(user_id, project_id, action="manage")
        skill = await self.repository.get(project_id, skill_space_id)
        if skill is None:
            raise ErrNotFound
        await self.repository.hard_delete(skill)
        await self.repository.commit()
        return {}

    async def get_download(self, project_id: str, skill_space_id: str, user_id: str):
        await self.ensure_project_access(user_id, project_id, action="read")
        skill = await self.repository.get(project_id, skill_space_id)
        if skill is None:
            raise ErrNotFound
        return skill

    async def get_download_public(self, project_id: str, skill_space_id: str):
        skill = await self.repository.get(project_id, skill_space_id)
        if skill is None:
            raise ErrNotFound
        return skill
