from __future__ import annotations

from typing import Any

from testing_agent.core.errors import (
    AppError,
    ErrNotFound,
    ErrRequirementFileMissing,
    ErrRequirementNameAlreadyUse,
)
from testing_agent.core.sid import new_id
from testing_agent.models.requirement import Requirement
from testing_agent.repositories.requirement import RequirementRepository
from testing_agent.schemas.requirement import (
    CreateRequirementRequest,
    RequirementResponse,
    UpdateRequirementRequest,
    normalize_document_type,
)
from testing_agent.services.common import list_payload
from testing_agent.services.project_access import ProjectAction
from testing_agent.services.sprint import SprintService


def dump_requirement(requirement: Requirement) -> dict:
    return RequirementResponse.model_validate(requirement).model_dump(by_alias=True, mode="json")


class RequirementService:
    def __init__(
        self,
        requirements: RequirementRepository,
        sprints: SprintService,
        files=None,
    ):
        self.requirements = requirements
        self.sprints = sprints
        self.files = files

    async def get_accessible_entity(
        self, user_id: str, requirement_id: str, *, action: ProjectAction = "read"
    ) -> Requirement:
        requirement = await self.requirements.get_active_by_id(requirement_id)
        if requirement is None:
            raise ErrNotFound
        await self.sprints.get_accessible_entity(user_id, requirement.sprint_id, action=action)
        return requirement

    async def create(
        self,
        user_id: str,
        sprint_id: str,
        body: CreateRequirementRequest,
    ) -> dict:
        await self.sprints.get_accessible_entity(user_id, sprint_id, action="write")
        existing = await self.requirements.get_active_by_sprint_and_name(sprint_id, body.name)
        if existing is not None:
            raise ErrRequirementNameAlreadyUse
        requirement = Requirement(
            requirement_id=new_id(),
            sprint_id=sprint_id,
            name=body.name,
            document_type=body.document_type,
            document_content="",
        )
        if body.document_file_id:
            await self._attach_file(user_id, requirement, body.document_file_id)
        elif body.document_content:
            raise AppError(400, "请先上传需求原文件到 S3，再提交 documentFileId", 400)
        self.requirements.add(requirement)
        await self.requirements.commit()
        await self.requirements.refresh(requirement)
        return dump_requirement(requirement)

    async def list(self, user_id: str, sprint_id: str) -> dict[str, Any]:
        await self.sprints.get_accessible_entity(user_id, sprint_id, action="read")
        rows = await self.requirements.list_active_by_sprint(sprint_id)
        return list_payload([dump_requirement(row) for row in rows])

    async def get(self, user_id: str, requirement_id: str) -> dict:
        return dump_requirement(
            await self.get_accessible_entity(user_id, requirement_id, action="read")
        )

    async def update(
        self,
        user_id: str,
        requirement_id: str,
        body: UpdateRequirementRequest,
    ) -> dict:
        requirement = await self.get_accessible_entity(user_id, requirement_id, action="write")
        if body.name is not None:
            requirement.name = body.name
        if body.document_type is not None:
            requirement.document_type = normalize_document_type(body.document_type)
        if body.document_file_id:
            await self._attach_file(user_id, requirement, body.document_file_id)
        elif body.document_content is not None:
            requirement.document_content = body.document_content
        await self.requirements.commit()
        await self.requirements.refresh(requirement)
        return dump_requirement(requirement)

    async def delete(self, user_id: str, requirement_id: str) -> dict:
        requirement = await self.get_accessible_entity(user_id, requirement_id, action="write")
        await self.requirements.hard_delete(requirement)
        await self.requirements.commit()
        return {}

    async def get_download(self, user_id: str, requirement_id: str) -> Requirement:
        requirement = await self.get_accessible_entity(user_id, requirement_id, action="read")
        if not getattr(requirement, "document_file_id", ""):
            raise ErrRequirementFileMissing
        return requirement

    async def _attach_file(self, user_id: str, requirement: Requirement, file_id: str):
        from testing_agent.core.errors import ErrBadRequest

        if self.files is None:
            raise ErrBadRequest
        sprint = await self.sprints.get_accessible_entity(
            user_id, requirement.sprint_id, action="write"
        )
        row = await self.files.attach(
            user_id,
            file_id,
            sprint.project_id,
            "requirement",
            requirement.requirement_id,
            purpose="requirement",
        )
        expected = "docx" if row.filename.lower().endswith(".docx") else "text"
        if requirement.document_type != expected:
            raise ErrBadRequest
        requirement.document_file_id = row.file_id
        requirement.document_filename = row.filename
        requirement.document_hash = row.sha256
        requirement.document_storage_path = ""
        requirement.document_content = ""
        requirement.document_download_url = (
            f"/v1/requirements/{requirement.requirement_id}/download"
        )
