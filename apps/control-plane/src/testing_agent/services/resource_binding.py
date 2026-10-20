from __future__ import annotations

from typing import Any

from testing_agent.core.enums import BindingStatus
from testing_agent.core.errors import (
    ErrBadRequest,
    ErrNotFound,
    dynamic_error,
)
from testing_agent.core.sid import new_id
from testing_agent.repositories.resource_binding import ResourceBindingRepository
from testing_agent.services.binding_support import dump_binding as dump_binding
from testing_agent.services.common import list_payload
from testing_agent.services.gitlab_bindings import GitLabBindings
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.project_access import ProjectAction, require_project_access
from testing_agent.services.resource_deletion import ResourceDeletion, SqlResourceDeletion
from testing_agent.services.zentao_bindings import ZentaoBindings

SUPPORTED_PROVIDERS = ("zentao", "gitlab")


class ResourceBindingService:
    def __init__(
        self,
        repository: ResourceBindingRepository,
        integration_connection_service: IntegrationConnectionService | None = None,
        zentao_resource_client: Any | None = None,
        *,
        zentao_access: Any | None = None,
        deletion: ResourceDeletion | None = None,
    ) -> None:
        self.deletion = deletion or SqlResourceDeletion()
        self.repository = repository
        self.integration_connection_service = integration_connection_service
        self.zentao_resource_client = zentao_resource_client
        self.zentao_access = zentao_access

    def gitlab_bindings(self) -> GitLabBindings:
        return GitLabBindings(
            self.repository,
            self.integration_connection_service,
            authorize=self.ensure_local_access,
            id_factory=new_id,
        )

    def zentao_bindings(self) -> ZentaoBindings:
        return ZentaoBindings(
            self.repository,
            self.integration_connection_service,
            authorize=self.ensure_local_access,
            id_factory=new_id,
            client=self.zentao_resource_client,
            access=self.zentao_access,
        )

    async def ensure_local_access(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        *,
        action: ProjectAction = "manage",
    ) -> str:
        if resource_type == "project":
            project_getter = self.repository.get_project
            if action != "read":
                project_getter = getattr(self.repository, "get_project_for_update", project_getter)
            project = await project_getter(resource_id)
            if project is None:
                raise ErrNotFound()
            await require_project_access(self.repository.session, user_id, project, action)
            return resource_id
        if resource_type == "sprint":
            sprint_getter = self.repository.get_sprint
            if action != "read":
                sprint_getter = getattr(self.repository, "get_sprint_for_update", sprint_getter)
            sprint = await sprint_getter(resource_id)
            if sprint is None:
                raise ErrNotFound()
            await self.ensure_local_access(user_id, "project", sprint.project_id, action=action)
            return sprint.project_id
        if resource_type == "requirement":
            requirement_getter = self.repository.get_requirement
            if action != "read":
                requirement_getter = getattr(
                    self.repository, "get_requirement_for_update", requirement_getter
                )
            requirement = await requirement_getter(resource_id)
            if requirement is None:
                raise ErrNotFound()
            sprint = await self.repository.get_sprint(requirement.sprint_id)
            if sprint is None:
                raise ErrNotFound()
            await self.ensure_local_access(user_id, "project", sprint.project_id, action=action)
            return sprint.project_id
        raise ErrNotFound()

    async def create(
        self, resource_type: str, resource_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        await self.ensure_local_access(user_id, resource_type, resource_id)
        provider = str(body.get("provider") or "").strip()
        if provider not in SUPPORTED_PROVIDERS:
            raise dynamic_error(ErrBadRequest, "provider 仅支持 zentao 或 gitlab")
        if provider == "zentao":
            return await self.zentao_bindings().create(resource_type, resource_id, body, user_id)
        return await self.gitlab_bindings().create(resource_type, resource_id, body, user_id)

    async def list(self, resource_type: str, resource_id: str, user_id: str) -> dict[str, Any]:
        await self.ensure_local_access(user_id, resource_type, resource_id, action="read")
        if resource_type == "project":
            return await self._list_project_bindings(resource_id, user_id)
        if resource_type == "requirement":
            return await self._list_requirement_bindings(resource_id, user_id)
        await self.ensure_local_access(user_id, resource_type, resource_id, action="read")
        rows = await self.repository.list(user_id, resource_type, resource_id)
        return list_payload([dump_binding(row) for row in rows])

    async def _list_project_bindings(self, project_id: str, user_id: str) -> dict[str, Any]:
        project = await self.repository.get_project(project_id)
        if project is None:
            raise ErrNotFound()
        rows = await self.repository.list_project_bindings(user_id, project_id)
        return list_payload([dump_binding(row) for row in rows])

    async def _list_requirement_bindings(self, requirement_id: str, user_id: str) -> dict[str, Any]:
        # gitlab 仓库绑定是项目级共享资产,查询不过滤 user_id(ADR-0007),
        # 与项目绑定列表同口径，禅道行也按项目共享。
        requirement = await self.repository.get_requirement(requirement_id)
        if requirement is None:
            raise ErrNotFound()
        rows = await self.repository.list_requirement_bindings(user_id, requirement_id)
        return list_payload([dump_binding(row) for row in rows])

    async def update(
        self,
        resource_type: str,
        resource_id: str,
        binding_id: str,
        body: dict[str, Any],
        user_id: str,
    ) -> dict:
        await self.ensure_local_access(user_id, resource_type, resource_id)
        binding = await self.repository.get(resource_type, resource_id, binding_id)
        if binding is None:
            raise ErrNotFound()
        if binding.provider == "zentao":
            return await self.zentao_bindings().update(binding, body, user_id)
        if binding.provider != "gitlab":
            raise dynamic_error(ErrBadRequest, "仅 GitLab 绑定支持更新")
        if binding.remote_resource_type == "group":
            return await self.gitlab_bindings().verify_group(binding, resource_id, body, user_id)
        if binding.remote_resource_type == "repository" and resource_type == "requirement":
            return await self.gitlab_bindings().update_requirement(binding, body, user_id)
        raise dynamic_error(ErrBadRequest, "仅 GitLab 绑定支持更新")

    async def delete(
        self, resource_type: str, resource_id: str, binding_id: str, user_id: str
    ) -> dict:
        await self.ensure_local_access(user_id, resource_type, resource_id)
        binding = await self.repository.get(resource_type, resource_id, binding_id)
        if binding is None:
            raise ErrNotFound()
        if binding.provider == "gitlab":
            binding = await self.gitlab_bindings().guard_delete(binding, resource_id)
            # Only project owners reach binding mutations.
            binding.status = BindingStatus.UNBOUND.value
            await self.deletion.delete(self.repository.session, binding)
            await self.repository.commit()
            return {}
        await self.ensure_local_access(user_id, resource_type, resource_id)
        binding.status = BindingStatus.UNBOUND.value
        await self.deletion.delete(self.repository.session, binding)
        await self.repository.commit()
        return {}
