from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from testing_agent.core.errors import ErrNotFound, ErrRequirementNameAlreadyUse
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


@dataclass(frozen=True, slots=True)
class RequirementDocumentFile:
    filename: str
    content: bytes


def document_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def safe_document_filename(filename: str, document_type: str) -> str:
    candidate = Path(filename).name.strip()
    if candidate:
        return candidate
    if normalize_document_type(document_type) == "docx":
        return "requirement.docx"
    return "requirement.txt"


class RequirementService:
    def __init__(
        self,
        requirements: RequirementRepository,
        sprints: SprintService,
        storage_root: str | Path = "storage",
    ):
        self.requirements = requirements
        self.sprints = sprints
        self.storage_root = Path(storage_root)

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
        document_file: RequirementDocumentFile | None = None,
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
        if document_file is not None:
            self._store_document_file(requirement, document_file)
        elif body.document_content:
            self._store_document_content(requirement, body.document_content)
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
        document_file: RequirementDocumentFile | None = None,
    ) -> dict:
        requirement = await self.get_accessible_entity(user_id, requirement_id, action="write")
        if body.name is not None:
            requirement.name = body.name
        if body.document_type is not None:
            requirement.document_type = normalize_document_type(body.document_type)
        if body.document_content is not None:
            requirement.document_content = body.document_content
        if document_file is not None:
            self._store_document_file(requirement, document_file)
        await self.requirements.commit()
        await self.requirements.refresh(requirement)
        return dump_requirement(requirement)

    async def delete(self, user_id: str, requirement_id: str) -> dict:
        requirement = await self.get_accessible_entity(user_id, requirement_id, action="write")
        await self.requirements.hard_delete(requirement)
        await self.requirements.commit()
        return {}

    async def upload_document(
        self,
        user_id: str,
        requirement_id: str,
        document_file: RequirementDocumentFile,
        document_type: str | None = None,
        document_content: str | None = None,
    ) -> dict:
        requirement = await self.get_accessible_entity(user_id, requirement_id, action="write")
        if document_type is not None:
            requirement.document_type = normalize_document_type(document_type)
        self._store_document_file(requirement, document_file)
        await self.requirements.commit()
        await self.requirements.refresh(requirement)
        return dump_requirement(requirement)

    async def get_download(self, user_id: str, requirement_id: str) -> Requirement:
        requirement = await self.get_accessible_entity(user_id, requirement_id, action="read")
        if not requirement.document_storage_path:
            raise ErrNotFound
        return requirement

    def _store_document_content(self, requirement: Requirement, content: str) -> None:
        filename = safe_document_filename("", requirement.document_type)
        self._write_document(
            requirement,
            filename,
            content.encode("utf-8"),
        )

    def _store_document_file(
        self, requirement: Requirement, document_file: RequirementDocumentFile
    ) -> None:
        filename = safe_document_filename(document_file.filename, requirement.document_type)
        self._write_document(
            requirement,
            filename,
            document_file.content,
        )

    def _write_document(
        self,
        requirement: Requirement,
        filename: str,
        content: bytes,
    ) -> None:
        storage_path = self.storage_root / "requirements" / requirement.requirement_id / filename
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_bytes(content)
        requirement.document_filename = filename
        requirement.document_hash = document_hash(content)
        requirement.document_storage_path = str(storage_path)
        requirement.document_download_url = (
            f"/v1/requirements/{requirement.requirement_id}/download"
        )
