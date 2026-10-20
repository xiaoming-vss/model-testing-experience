from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from testing_agent.core.enums import BindingStatus
from testing_agent.core.errors import (
    AppError,
    ErrBadRequest,
    ErrGroupBindingInUse,
    ErrIntegrationConnectionNotFound,
    ErrNotFound,
    ErrRemoteResourceAlreadyBound,
    ErrResourceBindingInvalid,
    dynamic_error,
)
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.repositories.resource_binding import ResourceBindingRepository
from testing_agent.services.binding_support import LocalBindingAccess, commit_binding, dump_binding
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.project_access import require_project_access
from testing_agent.services.service_instance import instance_key, normalize_instance_url


class GitLabBindings:
    def __init__(
        self,
        repository: ResourceBindingRepository,
        connections: IntegrationConnectionService | None,
        *,
        authorize: LocalBindingAccess,
        id_factory: Callable[[], str],
    ) -> None:
        self.repository = repository
        self.integration_connection_service = connections
        self.authorize = authorize
        self.new_id = id_factory

    async def create(
        self, resource_type: str, resource_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        if resource_type == "project":
            return await self._create_project(resource_id, body, user_id)
        if resource_type == "requirement":
            return await self._create_requirement(resource_id, body, user_id)
        raise dynamic_error(ErrBadRequest, "GitLab 绑定仅支持项目级群组绑定与需求级仓库绑定")

    async def _create_project(
        self,
        project_id: str,
        body: dict[str, Any],
        user_id: str,
    ) -> dict:
        project = await self.repository.get_project(project_id)
        if project is None:
            raise ErrNotFound()

        await require_project_access(self.repository.session, user_id, project, "manage")
        connection_id = str(body.get("connectionId") or body.get("connection_id") or "").strip()
        group_id = str(body.get("remoteResourceId") or body.get("remote_resource_id") or "").strip()
        if not connection_id or not group_id:
            raise ErrBadRequest()
        if self.integration_connection_service is None:
            raise ErrIntegrationConnectionNotFound()
        connection = await self.integration_connection_service.get_active_personal(
            user_id, "gitlab", connection_id, project_id
        )
        group_id = await self.integration_connection_service.resolve_gitlab_group_id(
            connection_id, project_id, group_id, user_id=user_id
        )
        if await self.repository.exists_active_project_group_binding(
            "gitlab", project_id, group_id, instance=instance_key(connection.base_url)
        ):
            raise ErrRemoteResourceAlreadyBound()

        binding = ResourceBinding(
            binding_id=self.new_id(),
            user_id=user_id,
            provider="gitlab",
            connection_id=connection_id,
            instance_url=normalize_instance_url(connection.base_url),
            instance_key=instance_key(connection.base_url),
            local_resource_type="project",
            local_resource_id=project_id,
            remote_resource_type="group",
            remote_resource_id=group_id,
            remote_parent_id="",
            remote_name_snapshot=str(
                body.get("remoteNameSnapshot") or body.get("remote_name_snapshot") or ""
            ),
            status=BindingStatus.ACTIVE.value,
            bound_at=datetime.now(UTC),
            extra_json=body.get("extraJson") or body.get("extra_json") or {},
        )
        self.repository.add(binding)
        await commit_binding(self.repository)
        await self.repository.refresh(binding)
        return dump_binding(binding)

    async def _requirement_project_id(self, requirement_id: str) -> str:
        requirement = await self.repository.get_requirement(requirement_id)
        if requirement is None:
            raise ErrNotFound()
        sprint = await self.repository.get_sprint(requirement.sprint_id)
        if sprint is None:
            raise ErrNotFound()
        return sprint.project_id

    async def _ensure_repository_in_group(
        self,
        user_id: str,
        project_id: str,
        group_id: str,
        repository_id: str,
        body: dict[str, Any],
    ) -> tuple[str, ResourceBinding]:
        service = self.integration_connection_service
        if service is None:
            raise ErrIntegrationConnectionNotFound()
        connection_id = str(body.get("connectionId") or "")
        url = str(body.get("instanceUrl") or "")
        if connection_id:
            connection = await service.get_active_personal(
                user_id, "gitlab", connection_id, project_id
            )
            url = connection.base_url
        group = await self.repository.get_active_project_group_binding(
            "gitlab",
            project_id,
            group_id,
            for_update=True,
            instance=instance_key(url) if url else None,
        )
        if group is None:
            raise ErrResourceBindingInvalid()
        connection = await service.resolve_personal_connection(
            user_id, "gitlab", project_id, group.instance_url, connection_id
        )
        canonical = await service.ensure_gitlab_repository_scope(
            connection.connection_id, project_id, group_id, repository_id, user_id=user_id
        )
        return canonical, group

    async def _create_requirement(
        self,
        requirement_id: str,
        body: dict[str, Any],
        user_id: str,
    ) -> dict:
        await self.authorize(user_id, "requirement", requirement_id)
        project_id = await self._requirement_project_id(requirement_id)
        repository_id = str(
            body.get("remoteResourceId") or body.get("remote_resource_id") or ""
        ).strip()
        group_id = str(body.get("remoteParentId") or body.get("remote_parent_id") or "").strip()
        if not repository_id or not group_id:
            raise ErrBadRequest()
        extra = body.get("extraJson") or body.get("extra_json") or {}
        branch = str(extra.get("branch") or "").strip()
        if not branch:
            raise dynamic_error(ErrResourceBindingInvalid, "绑定仓库必须携带 branch")
        baseline_branch = str(
            extra.get("baseline_branch") or extra.get("baselineBranch") or ""
        ).strip()

        repository_id, group = await self._ensure_repository_in_group(
            user_id, project_id, group_id, repository_id, body
        )
        if await self.repository.exists_active_requirement_repo_binding(
            requirement_id, repository_id, instance=group.instance_key
        ):
            raise ErrRemoteResourceAlreadyBound()

        binding = ResourceBinding(
            binding_id=self.new_id(),
            user_id=user_id,
            provider="gitlab",
            connection_id="",
            instance_url=group.instance_url,
            instance_key=group.instance_key,
            local_resource_type="requirement",
            local_resource_id=requirement_id,
            remote_resource_type="repository",
            remote_resource_id=repository_id,
            remote_parent_id=group_id,
            remote_name_snapshot=str(
                body.get("remoteNameSnapshot") or body.get("remote_name_snapshot") or ""
            ),
            status=BindingStatus.ACTIVE.value,
            bound_at=datetime.now(UTC),
            extra_json={
                "branch": branch,
                **({"baseline_branch": baseline_branch} if baseline_branch else {}),
            },
        )
        self.repository.add(binding)
        await commit_binding(self.repository)
        await self.repository.refresh(binding)
        return dump_binding(binding)

    async def verify_group(
        self,
        binding: ResourceBinding,
        project_id: str,
        body: dict[str, Any],
        user_id: str,
    ) -> dict:
        connection_id = str(body.get("connectionId") or body.get("connection_id") or "").strip()
        if not connection_id:
            raise ErrBadRequest()
        if self.integration_connection_service is None:
            raise ErrIntegrationConnectionNotFound()
        # Reverify the same resource using the current owner's personal authorization.
        connection = await self.integration_connection_service.get_active_personal(
            user_id, "gitlab", connection_id, project_id
        )
        if instance_key(connection.base_url) != binding.instance_key:
            raise ErrResourceBindingInvalid()
        await self.integration_connection_service.resolve_gitlab_group_id(
            connection_id, project_id, binding.remote_resource_id, user_id=user_id
        )
        binding.last_verified_at = datetime.now(UTC)
        await commit_binding(self.repository)
        await self.repository.refresh(binding)
        return dump_binding(binding)

    async def update_requirement(
        self,
        binding: ResourceBinding,
        body: dict[str, Any],
        user_id: str,
    ) -> dict:
        # 更新仅覆盖分支与基线分支;换仓库/换凭据来源群组走解绑重建。
        project_id = await self._requirement_project_id(binding.local_resource_id)
        await self._ensure_repository_in_group(
            user_id,
            project_id,
            binding.remote_parent_id,
            binding.remote_resource_id,
            {**body, "instanceUrl": binding.instance_url},
        )
        extra = dict(binding.extra_json or {})
        branch = body.get("branch")
        if branch is not None:
            branch_value = str(branch or "").strip()
            if not branch_value:
                raise dynamic_error(ErrResourceBindingInvalid, "绑定仓库必须携带 branch")
            extra["branch"] = branch_value
        if "baselineBranch" in body or "baseline_branch" in body:
            baseline = body.get("baselineBranch", body.get("baseline_branch"))
            baseline_value = str(baseline or "").strip()
            if baseline_value:
                extra["baseline_branch"] = baseline_value
            else:
                extra.pop("baseline_branch", None)
        binding.extra_json = extra
        await self.repository.commit()
        await self.repository.refresh(binding)
        return dump_binding(binding)

    async def guard_delete(self, binding: ResourceBinding, resource_id: str) -> ResourceBinding:
        if binding.remote_resource_type == "group":
            # Serialize group deletion with requirement binding creation.
            locked = await self.repository.get_active_project_group_binding(
                "gitlab",
                resource_id,
                binding.remote_resource_id,
                for_update=True,
                instance=binding.instance_key,
            )
            if locked is None or locked.binding_id != binding.binding_id:
                raise ErrNotFound()
            binding = locked
            # 删除保护(ADR-0007):需求绑定经由所属群组的项目绑定约束资源范围,
            # 若仍有激活需求绑定引用该群组下仓库,阻止删除并返回受影响清单。
            affected = await self.repository.list_active_requirement_repo_bindings_for_group(
                resource_id, binding.remote_resource_id, instance=binding.instance_key
            )
            if affected:
                raise AppError(
                    ErrGroupBindingInUse.code,
                    ErrGroupBindingInUse.message,
                    ErrGroupBindingInUse.http_code,
                    {"bindings": [dump_binding(row) for row in affected]},
                )
        return binding
