from __future__ import annotations

from http import HTTPStatus
from typing import Any

from sqlalchemy.exc import IntegrityError

from testing_agent.core.errors import (
    AppError,
    ErrBadRequest,
    ErrSoftwareRepositoryHasInterfaces,
    ErrSoftwareRepositoryHasRequirements,
    ErrSoftwareRepositoryHasUiElementGroups,
    ErrSoftwareRepositoryNameAlreadyUse,
    ErrSoftwareRepositoryNotFound,
    ErrSoftwareRepositoryRepositoryInvalid,
    dynamic_error,
)
from testing_agent.core.sid import new_id
from testing_agent.domain.api_interface import normalize_base_path
from testing_agent.models.software_repository import SoftwareRepository
from testing_agent.repositories.requirement_software_repository import (
    RequirementSoftwareRepositoryRepository,
)
from testing_agent.repositories.software_repository import SoftwareRepositoryRepository
from testing_agent.schemas.software_repository import (
    SoftwareRepositoryCreateRequest,
    SoftwareRepositoryPayload,
    SoftwareRepositoryResponse,
    SoftwareRepositoryUpdateRequest,
)
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.project_access import ProjectAction, require_project_id
from testing_agent.services.resource_deletion import ResourceDeletion, SqlResourceDeletion
from testing_agent.services.service_instance import instance_key, normalize_instance_url


def dump_software_repository(repository: SoftwareRepository) -> dict[str, Any]:
    git_repository = None
    if repository.repository_project_id:
        git_repository = {
            "project_id": repository.repository_project_id,
            "path": repository.repository_path,
            "name": repository.repository_name,
            "instance_url": repository.repository_instance_url,
        }
    data = {
        "software_repository_id": repository.software_repository_id,
        "project_id": repository.project_id,
        "name": repository.name,
        "description": repository.description,
        "base_path": repository.base_path,
        "repository": git_repository,
        "interface_groups": repository.interface_groups_json or [],
        "interface_count": getattr(repository, "interface_count", 0),
        "version": repository.version,
        "created_at": repository.created_at,
        "updated_at": repository.updated_at,
    }
    return SoftwareRepositoryResponse.model_validate(data).model_dump(by_alias=True, mode="json")


class SoftwareRepositoryService:
    def __init__(
        self,
        repository: SoftwareRepositoryRepository,
        connections: IntegrationConnectionService | None = None,
        *,
        requirements: RequirementSoftwareRepositoryRepository | None = None,
        deletion: ResourceDeletion | None = None,
    ) -> None:
        self.repository = repository
        self.connections = connections
        self.requirements = requirements or RequirementSoftwareRepositoryRepository(
            repository.session
        )
        self.deletion = deletion or SqlResourceDeletion()

    async def list(self, user_id: str, project_id: str) -> dict[str, Any]:
        await require_project_id(self.repository.session, user_id, project_id, action="read")
        repositories = await self.repository.list_by_project(project_id)
        return {
            "items": [dump_software_repository(item) for item in repositories],
            "total": len(repositories),
        }

    async def get(self, user_id: str, software_repository_id: str) -> dict[str, Any]:
        repository = await self._accessible_repository(
            user_id, software_repository_id, action="read"
        )
        await self._attach_counts(repository)
        return dump_software_repository(repository)

    async def create(
        self, user_id: str, project_id: str, body: SoftwareRepositoryCreateRequest
    ) -> dict[str, Any]:
        await require_project_id(self.repository.session, user_id, project_id, action="manage")
        name = self._name(body.name)
        description = body.description.strip()
        base_path = self._base_path(body.base_path)
        repository = await self._repository_values(user_id, project_id, body.repository)
        if await self.repository.get_by_project_and_name(project_id, name) is not None:
            raise ErrSoftwareRepositoryNameAlreadyUse()
        software_repository = SoftwareRepository(
            software_repository_id=new_id(),
            project_id=project_id,
            name=name,
            description=description,
            base_path=base_path,
            version=1,
            created_by_user_id=user_id,
            **repository,
        )
        self.repository.add(software_repository)
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ErrSoftwareRepositoryNameAlreadyUse() from exc
        await self.repository.refresh(software_repository)
        await self._attach_counts(software_repository)
        return dump_software_repository(software_repository)

    async def update(
        self, user_id: str, software_repository_id: str, body: SoftwareRepositoryUpdateRequest
    ) -> dict[str, Any]:
        software_repository = await self._accessible_repository(
            user_id, software_repository_id, action="manage", for_update=True
        )
        fields = body.model_fields_set
        changed = False
        if "name" in fields:
            if body.name is None:
                raise ErrBadRequest()
            name = self._name(body.name)
            if name != software_repository.name:
                if (
                    await self.repository.get_by_project_and_name(
                        software_repository.project_id,
                        name,
                        exclude_software_repository_id=software_repository.software_repository_id,
                    )
                    is not None
                ):
                    raise ErrSoftwareRepositoryNameAlreadyUse()
                software_repository.name = name
                changed = True
        if "description" in fields:
            if body.description is None:
                raise ErrBadRequest()
            description = body.description.strip()
            if description != software_repository.description:
                software_repository.description = description
                changed = True
        if "base_path" in fields:
            if body.base_path is None:
                raise ErrBadRequest()
            base_path = self._base_path(body.base_path)
            if base_path != software_repository.base_path:
                software_repository.base_path = base_path
                changed = True
        if "repository" in fields:
            if body.repository is None:
                raise dynamic_error(ErrBadRequest, "软件仓库必须绑定 Git 仓库，不能清除")
            repository = await self._repository_values(
                user_id, software_repository.project_id, body.repository
            )
            identity_changed = any(
                getattr(software_repository, key) != repository[key]
                for key in ("repository_project_id", "repository_instance_key")
            )
            if identity_changed and await self.repository.has_ui_element_groups(
                software_repository_id
            ):
                raise ErrSoftwareRepositoryHasUiElementGroups()
            repository_changed = any(
                getattr(software_repository, key) != value for key, value in repository.items()
            )
            if repository_changed:
                for key, value in repository.items():
                    setattr(software_repository, key, value)
                await self.requirements.clear_branches_for_repository(
                    software_repository.software_repository_id
                )
                changed = True
        if changed:
            software_repository.version += 1
            try:
                await self.repository.commit()
            except IntegrityError as exc:
                await self.repository.rollback()
                raise ErrSoftwareRepositoryNameAlreadyUse() from exc
            await self.repository.refresh(software_repository)
        await self._attach_counts(software_repository)
        return dump_software_repository(software_repository)

    async def delete(self, user_id: str, software_repository_id: str) -> dict[str, Any]:
        software_repository = await self.repository.get_for_update(software_repository_id)
        if software_repository is None:
            raise ErrSoftwareRepositoryNotFound()
        await require_project_id(
            self.repository.session, user_id, software_repository.project_id, action="manage"
        )
        if await self.repository.count_interfaces(software_repository_id) > 0:
            raise ErrSoftwareRepositoryHasInterfaces()
        if await self.requirements.count_for_repository(software_repository_id) > 0:
            raise ErrSoftwareRepositoryHasRequirements()
        if await self.repository.has_ui_element_groups(software_repository_id):
            raise ErrSoftwareRepositoryHasUiElementGroups()
        await self.deletion.delete(self.repository.session, software_repository)
        await self.repository.commit()
        return {}

    async def _accessible_repository(
        self,
        user_id: str,
        software_repository_id: str,
        *,
        action: ProjectAction,
        for_update: bool = False,
    ) -> SoftwareRepository:
        repository = (
            await self.repository.get_for_update(software_repository_id)
            if for_update
            else await self.repository.get(software_repository_id)
        )
        if repository is None:
            raise ErrSoftwareRepositoryNotFound()
        await require_project_id(
            self.repository.session, user_id, repository.project_id, action=action
        )
        return repository

    async def _attach_counts(self, repository: SoftwareRepository) -> None:
        repository.interface_count = await self.repository.count_interfaces(
            repository.software_repository_id
        )

    def _name(self, value: str) -> str:
        name = str(value or "").strip()
        if not name or len(name) > 100:
            raise ErrBadRequest()
        return name

    def _base_path(self, value: str) -> str:
        try:
            return normalize_base_path(value)
        except ValueError as exc:
            raise dynamic_error(ErrBadRequest, str(exc)) from exc

    async def _repository_values(
        self,
        user_id: str,
        project_id: str,
        repository: SoftwareRepositoryPayload,
    ) -> dict[str, str]:
        if self.connections is None:
            raise ErrSoftwareRepositoryRepositoryInvalid()
        try:
            connection = await self.connections.get_active_personal(
                user_id, "gitlab", repository.connection_id, project_id
            )
            canonical_id = await self.connections.ensure_gitlab_repository_scope(
                repository.connection_id,
                project_id,
                repository.group_id,
                repository.repository_id,
                user_id=user_id,
            )
            project = await self.connections.get_gitlab_project(
                repository.connection_id,
                project_id,
                canonical_id,
                user_id=user_id,
            )
        except AppError as exc:
            if exc.http_code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
                raise
            raise dynamic_error(ErrSoftwareRepositoryRepositoryInvalid, exc.message) from exc
        path = str(project.get("pathWithNamespace") or "").strip()
        if not path:
            raise ErrSoftwareRepositoryRepositoryInvalid()
        return {
            "repository_project_id": canonical_id,
            "repository_group_id": repository.group_id,
            "repository_instance_key": instance_key(connection.base_url),
            "repository_path": path,
            "repository_name": path.rsplit("/", 1)[-1],
            "repository_instance_url": normalize_instance_url(connection.base_url),
        }


__all__ = ["SoftwareRepositoryService", "dump_software_repository"]
