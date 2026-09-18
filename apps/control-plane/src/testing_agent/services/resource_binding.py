from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from testing_agent.core.enums import BindingStatus
from testing_agent.core.errors import (
    AppError,
    ErrBadRequest,
    ErrGroupBindingInUse,
    ErrIntegrationConnectionNotFound,
    ErrNotFound,
    ErrRemoteResourceAlreadyBound,
    ErrResourceBindingAlreadyExists,
    ErrResourceBindingInvalid,
    ErrZentaoRemoteResourceUnavailable,
    dynamic_error,
)
from testing_agent.core.sid import new_id
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.repositories.resource_binding import ResourceBindingRepository
from testing_agent.services.common import list_payload
from testing_agent.services.integration_connection import IntegrationConnectionService, item_value
from testing_agent.services.project_access import ProjectAction, require_project_access
from testing_agent.services.service_instance import instance_key, normalize_instance_url
from testing_agent.services.zentao_resource import parse_zentao_remote_id, truncate_error


def dump_binding(binding: ResourceBinding) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "bindingId": binding.binding_id,
        "instanceUrl": binding.instance_url,
        "provider": binding.provider,
        "connectionId": binding.connection_id,
        "localResourceType": binding.local_resource_type,
        "localResourceId": binding.local_resource_id,
        "remoteResourceType": binding.remote_resource_type,
        "remoteResourceId": binding.remote_resource_id,
        "remoteParentId": binding.remote_parent_id,
        "remoteNameSnapshot": binding.remote_name_snapshot,
        "status": binding.status,
        "boundAt": binding.bound_at,
        "lastVerifiedAt": binding.last_verified_at,
        "createdAt": binding.created_at,
        "updatedAt": binding.updated_at,
    }
    if binding.remote_resource_type == "repository":
        extra = getattr(binding, "extra_json", None) or {}
        payload["branch"] = str(extra.get("branch") or "")
        payload["baselineBranch"] = str(
            extra.get("baseline_branch") or extra.get("baselineBranch") or ""
        )
    return payload


ZENTAO_REMOTE_TYPE_DEFAULTS = {
    "project": "project",
    "sprint": "execution",
    "requirement": "story",
}

SUPPORTED_PROVIDERS = ("zentao", "gitlab")


class ResourceBindingService:
    def __init__(
        self,
        repository: ResourceBindingRepository,
        integration_connection_service: IntegrationConnectionService | None = None,
        zentao_resource_client: Any | None = None,
    ):
        self.repository = repository
        self.integration_connection_service = integration_connection_service
        self.zentao_resource_client = zentao_resource_client

    async def ensure_local_access(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        *,
        action: ProjectAction = "manage",
    ) -> str:
        if resource_type == "project":
            project = await self.repository.get_project(resource_id)
            if project is None:
                raise ErrNotFound
            await require_project_access(self.repository.session, user_id, project, action)
            return resource_id
        if resource_type == "sprint":
            sprint = await self.repository.get_sprint(resource_id)
            if sprint is None:
                raise ErrNotFound
            await self.ensure_local_access(user_id, "project", sprint.project_id, action=action)
            return sprint.project_id
        if resource_type == "requirement":
            requirement = await self.repository.get_requirement(resource_id)
            if requirement is None:
                raise ErrNotFound
            sprint = await self.repository.get_sprint(requirement.sprint_id)
            if sprint is None:
                raise ErrNotFound
            await self.ensure_local_access(user_id, "project", sprint.project_id, action=action)
            return sprint.project_id
        raise ErrNotFound

    async def create(
        self, resource_type: str, resource_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        await self.ensure_local_access(user_id, resource_type, resource_id)
        provider = str(body.get("provider") or "").strip()
        if provider not in SUPPORTED_PROVIDERS:
            raise dynamic_error(ErrBadRequest, "provider 仅支持 zentao 或 gitlab")
        if provider == "zentao":
            return await self._create_zentao_binding(resource_type, resource_id, body, user_id)
        return await self._create_gitlab_binding(resource_type, resource_id, body, user_id)

    async def _create_zentao_binding(
        self, resource_type: str, resource_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        if resource_type == "project":
            return await self._create_zentao_project_binding(resource_id, body, user_id)

        project_id = await self.ensure_local_access(user_id, resource_type, resource_id)
        service = self.integration_connection_service
        if service is None or self.zentao_resource_client is None:
            raise ErrIntegrationConnectionNotFound
        connection_id = str(body.get("connectionId") or "")
        connection = await service.get_active_personal(user_id, "zentao", connection_id, project_id)
        connection = await service.resolve_zentao_access(user_id, connection_id, project_id)
        if resource_type == "sprint":
            parent = await self.repository.get_active_by_local_resource("project", project_id)
        else:
            requirement = await self.repository.get_requirement(resource_id)
            if requirement is None:
                raise ErrNotFound
            parent = await self.repository.get_active_by_local_resource(
                "sprint", requirement.sprint_id
            )
        if (
            parent is None
            or parent.provider != "zentao"
            or parent.instance_key != instance_key(connection.base_url)
        ):
            raise ErrResourceBindingInvalid
        try:
            remote_id = str(parse_zentao_remote_id(str(body.get("remoteResourceId") or "")))
        except ValueError as exc:
            raise dynamic_error(ErrResourceBindingInvalid, str(exc)) from exc
        requested_parent = str(body.get("remoteParentId") or "")
        if requested_parent and requested_parent != parent.remote_resource_id:
            raise ErrResourceBindingInvalid
        found = False
        page = 1
        while True:
            if resource_type == "sprint":
                result = await self.zentao_resource_client.list_project_executions(
                    connection, parent.remote_resource_id, page=page, page_size=100
                )
            else:
                # Stories are returned as a complete list, without pagination parameters.
                result = await self.zentao_resource_client.list_execution_stories(
                    connection, parent.remote_resource_id
                )
            items = result.get("items") or []
            if any(
                str(item_value(item, "id")) == remote_id
                and not item_value(item, "deleted", default=False)
                for item in items
            ):
                found = True
                break
            if (
                resource_type != "sprint"
                or not items
                or page * 100 >= int(result.get("total") or len(items))
            ):
                break
            page += 1
        if not found:
            raise ErrResourceBindingInvalid
        body = {**body, "remoteResourceId": remote_id, "remoteParentId": parent.remote_resource_id}
        binding = ResourceBinding(
            binding_id=new_id(),
            user_id=user_id,
            provider="zentao",
            connection_id=connection_id,
            instance_url=normalize_instance_url(connection.base_url),
            instance_key=instance_key(connection.base_url),
            local_resource_type=resource_type,
            local_resource_id=resource_id,
            remote_resource_type=str(
                body.get("remoteResourceType")
                or body.get("remote_resource_type")
                or ZENTAO_REMOTE_TYPE_DEFAULTS.get(resource_type, resource_type)
            ),
            remote_resource_id=str(
                body.get("remoteResourceId") or body.get("remote_resource_id") or ""
            ),
            remote_parent_id=str(body.get("remoteParentId") or body.get("remote_parent_id") or ""),
            remote_name_snapshot=str(
                body.get("remoteNameSnapshot") or body.get("remote_name_snapshot") or ""
            ),
            status=BindingStatus.ACTIVE.value,
            bound_at=datetime.now(UTC),
            extra_json=body.get("extraJson") or body.get("extra_json") or {},
        )
        self.repository.add(binding)
        await self._commit_binding()
        await self.repository.refresh(binding)
        return dump_binding(binding)

    async def _create_gitlab_binding(
        self, resource_type: str, resource_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        if resource_type == "project":
            return await self._create_gitlab_project_binding(resource_id, body, user_id)
        if resource_type == "requirement":
            return await self._create_gitlab_requirement_binding(resource_id, body, user_id)
        raise dynamic_error(ErrBadRequest, "GitLab 绑定仅支持项目级群组绑定与需求级仓库绑定")

    async def _create_gitlab_project_binding(
        self,
        project_id: str,
        body: dict[str, Any],
        user_id: str,
    ) -> dict:
        project = await self.repository.get_project(project_id)
        if project is None:
            raise ErrNotFound

        await require_project_access(self.repository.session, user_id, project, "manage")
        connection_id = str(body.get("connectionId") or body.get("connection_id") or "").strip()
        group_id = str(body.get("remoteResourceId") or body.get("remote_resource_id") or "").strip()
        if not connection_id or not group_id:
            raise ErrBadRequest
        if self.integration_connection_service is None:
            raise ErrIntegrationConnectionNotFound
        connection = await self.integration_connection_service.get_active_personal(
            user_id, "gitlab", connection_id, project_id
        )
        group_id = await self.integration_connection_service.resolve_gitlab_group_id(
            connection_id, project_id, group_id, user_id=user_id
        )
        if await self.repository.exists_active_project_group_binding(
            "gitlab", project_id, group_id, instance=instance_key(connection.base_url)
        ):
            raise ErrRemoteResourceAlreadyBound

        binding = ResourceBinding(
            binding_id=new_id(),
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
        await self._commit_binding()
        await self.repository.refresh(binding)
        return dump_binding(binding)

    async def _requirement_project_id(self, requirement_id: str) -> str:
        requirement = await self.repository.get_requirement(requirement_id)
        if requirement is None:
            raise ErrNotFound
        sprint = await self.repository.get_sprint(requirement.sprint_id)
        if sprint is None:
            raise ErrNotFound
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
            raise ErrIntegrationConnectionNotFound
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
            raise ErrResourceBindingInvalid
        connection = await service.resolve_personal_connection(
            user_id, "gitlab", project_id, group.instance_url, connection_id
        )
        canonical = await service.ensure_gitlab_repository_scope(
            connection.connection_id, project_id, group_id, repository_id, user_id=user_id
        )
        return canonical, group

    async def _commit_binding(self) -> None:
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            # Translate only our known uniqueness constraint, not unrelated DB errors.
            if "uq_binding_resource" in str(
                exc.orig
            ) or "UNIQUE constraint failed: resource_bindings." in str(exc.orig):
                raise ErrRemoteResourceAlreadyBound from exc
            raise

    async def _create_gitlab_requirement_binding(
        self,
        requirement_id: str,
        body: dict[str, Any],
        user_id: str,
    ) -> dict:
        await self.ensure_local_access(user_id, "requirement", requirement_id)
        project_id = await self._requirement_project_id(requirement_id)
        repository_id = str(
            body.get("remoteResourceId") or body.get("remote_resource_id") or ""
        ).strip()
        group_id = str(body.get("remoteParentId") or body.get("remote_parent_id") or "").strip()
        if not repository_id or not group_id:
            raise ErrBadRequest
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
            raise ErrRemoteResourceAlreadyBound

        binding = ResourceBinding(
            binding_id=new_id(),
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
        await self._commit_binding()
        await self.repository.refresh(binding)
        return dump_binding(binding)

    async def _create_zentao_project_binding(
        self,
        project_id: str,
        body: dict[str, Any],
        user_id: str,
    ) -> dict:
        project = await self.repository.get_project(project_id)
        if project is None:
            raise ErrNotFound
        await require_project_access(self.repository.session, user_id, project, "manage")

        provider = "zentao"
        connection_id = str(body.get("connectionId") or body.get("connection_id") or "").strip()
        remote_resource_id = str(
            body.get("remoteResourceId") or body.get("remote_resource_id") or ""
        ).strip()
        if not connection_id or not remote_resource_id:
            raise ErrBadRequest
        try:
            parse_zentao_remote_id(remote_resource_id)
        except ValueError as exc:
            raise dynamic_error(ErrResourceBindingInvalid, str(exc)) from exc

        existing_local = await self.repository.get_active_by_local_resource("project", project_id)
        if existing_local is not None:
            raise ErrResourceBindingAlreadyExists

        if self.integration_connection_service is None:
            raise ErrIntegrationConnectionNotFound
        await self.integration_connection_service.get_active_personal(
            user_id, "zentao", connection_id, project_id
        )
        connection = await self.integration_connection_service.resolve_zentao_access(
            user_id, connection_id, project_id
        )

        if self.zentao_resource_client is None:
            raise ErrZentaoRemoteResourceUnavailable
        try:
            remote_project = await self.zentao_resource_client.get_project(
                connection,
                remote_resource_id,
            )
        except Exception as exc:
            raise dynamic_error(
                ErrZentaoRemoteResourceUnavailable,
                truncate_error(str(exc)),
            ) from exc
        if bool(getattr(remote_project, "deleted", False)):
            raise dynamic_error(ErrZentaoRemoteResourceUnavailable, "禅道项目已删除")

        remote_project_id = str(int(remote_project.id))
        remote_exists = await self.repository.exists_active_by_remote_resource(
            provider,
            connection_id,
            "project",
            remote_project_id,
        )
        if remote_exists:
            raise ErrRemoteResourceAlreadyBound

        now = datetime.now(UTC)
        binding = ResourceBinding(
            binding_id=new_id(),
            user_id=user_id,
            provider=provider,
            connection_id=connection_id,
            instance_url=normalize_instance_url(connection.base_url),
            instance_key=instance_key(connection.base_url),
            local_resource_type="project",
            local_resource_id=project_id,
            remote_resource_type="project",
            remote_resource_id=remote_project_id,
            remote_parent_id="",
            remote_name_snapshot=str(getattr(remote_project, "name", "") or ""),
            status=BindingStatus.ACTIVE.value,
            bound_at=now,
            last_verified_at=now,
            extra_json={},
        )
        self.repository.add(binding)
        await self._commit_binding()
        await self.repository.refresh(binding)
        return dump_binding(binding)

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
            raise ErrNotFound
        rows = await self.repository.list_project_bindings(user_id, project_id)
        return list_payload([dump_binding(row) for row in rows])

    async def _list_requirement_bindings(self, requirement_id: str, user_id: str) -> dict[str, Any]:
        # gitlab 仓库绑定是项目级共享资产,查询不过滤 user_id(ADR-0007),
        # 与项目绑定列表同口径，禅道行也按项目共享。
        requirement = await self.repository.get_requirement(requirement_id)
        if requirement is None:
            raise ErrNotFound
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
            raise ErrNotFound
        if binding.provider == "zentao":
            return await self._update_zentao_binding(binding, body, user_id)
        if binding.provider != "gitlab":
            raise dynamic_error(ErrBadRequest, "仅 GitLab 绑定支持更新")
        if binding.remote_resource_type == "group":
            return await self._verify_gitlab_group_binding(binding, resource_id, body, user_id)
        if binding.remote_resource_type == "repository" and resource_type == "requirement":
            return await self._update_gitlab_requirement_binding(binding, body, user_id)
        raise dynamic_error(ErrBadRequest, "仅 GitLab 绑定支持更新")

    async def _update_zentao_binding(self, binding, body, user_id):
        project_id = await self.ensure_local_access(
            user_id, binding.local_resource_type, binding.local_resource_id
        )
        if self.integration_connection_service is None or self.zentao_resource_client is None:
            raise ErrIntegrationConnectionNotFound
        connection = await self.integration_connection_service.resolve_personal_connection(
            user_id, "zentao", project_id, binding.instance_url, str(body.get("connectionId") or "")
        )
        connection = await self.integration_connection_service.resolve_zentao_access(
            user_id, connection.connection_id, project_id
        )
        remote_id = str(body.get("remoteResourceId") or binding.remote_resource_id)
        try:
            parse_zentao_remote_id(remote_id)
        except ValueError as exc:
            raise ErrResourceBindingInvalid from exc
        if remote_id != binding.remote_resource_id:
            child_type = {"project": "execution", "sprint": "story"}.get(
                binding.local_resource_type
            )
            if child_type and await self.repository.session.scalar(
                select(ResourceBinding.id)
                .where(
                    ResourceBinding.provider == "zentao",
                    ResourceBinding.instance_key == binding.instance_key,
                    ResourceBinding.remote_resource_type == child_type,
                    ResourceBinding.remote_parent_id == binding.remote_resource_id,
                    ResourceBinding.status == "active",
                )
                .limit(1)
            ):
                raise ErrResourceBindingInvalid
        if binding.local_resource_type == "project":
            remote = await self.zentao_resource_client.get_project(connection, remote_id)
            if item_value(remote, "deleted", default=False):
                raise ErrResourceBindingInvalid
        else:
            if binding.local_resource_type == "sprint":
                parent = await self.repository.get_active_by_local_resource("project", project_id)
            else:
                requirement = await self.repository.get_requirement(binding.local_resource_id)
                if requirement is None:
                    raise ErrNotFound
                parent = await self.repository.get_active_by_local_resource(
                    "sprint", requirement.sprint_id
                )
            if (
                parent is None
                or parent.provider != "zentao"
                or parent.instance_key != binding.instance_key
            ):
                raise ErrResourceBindingInvalid
            try:
                parent_id = str(parse_zentao_remote_id(parent.remote_resource_id))
            except ValueError as exc:
                raise ErrResourceBindingInvalid from exc
            if binding.remote_parent_id and binding.remote_parent_id != parent_id:
                raise ErrResourceBindingInvalid
            page = 1
            while True:
                if binding.local_resource_type == "sprint":
                    result = await self.zentao_resource_client.list_project_executions(
                        connection, parent_id, page=page, page_size=100
                    )
                else:
                    result = await self.zentao_resource_client.list_execution_stories(
                        connection, parent_id
                    )
                items = result.get("items") or []
                if any(
                    str(item_value(item, "id")) == remote_id
                    and not item_value(item, "deleted", default=False)
                    for item in items
                ):
                    break
                if (
                    binding.local_resource_type != "sprint"
                    or not items
                    or page * 100 >= int(result.get("total") or len(items))
                ):
                    raise ErrResourceBindingInvalid
                page += 1
            binding.remote_parent_id = parent_id
        binding.remote_resource_id = remote_id
        binding.last_verified_at = datetime.now(UTC)
        await self._commit_binding()
        await self.repository.refresh(binding)
        return dump_binding(binding)

    async def _verify_gitlab_group_binding(
        self,
        binding: ResourceBinding,
        project_id: str,
        body: dict[str, Any],
        user_id: str,
    ) -> dict:
        connection_id = str(body.get("connectionId") or body.get("connection_id") or "").strip()
        if not connection_id:
            raise ErrBadRequest
        if self.integration_connection_service is None:
            raise ErrIntegrationConnectionNotFound
        # Reverify the same resource using the current owner's personal authorization.
        connection = await self.integration_connection_service.get_active_personal(
            user_id, "gitlab", connection_id, project_id
        )
        if instance_key(connection.base_url) != binding.instance_key:
            raise ErrResourceBindingInvalid
        await self.integration_connection_service.resolve_gitlab_group_id(
            connection_id, project_id, binding.remote_resource_id, user_id=user_id
        )
        binding.last_verified_at = datetime.now(UTC)
        await self._commit_binding()
        await self.repository.refresh(binding)
        return dump_binding(binding)

    async def _update_gitlab_requirement_binding(
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

    async def delete(
        self, resource_type: str, resource_id: str, binding_id: str, user_id: str
    ) -> dict:
        await self.ensure_local_access(user_id, resource_type, resource_id)
        binding = await self.repository.get(resource_type, resource_id, binding_id)
        if binding is None:
            raise ErrNotFound
        if binding.provider == "gitlab":
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
                    raise ErrNotFound
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
            # Only project owners reach binding mutations.
            binding.status = BindingStatus.UNBOUND.value
            await self.repository.hard_delete(binding)
            await self.repository.commit()
            return {}
        await self.ensure_local_access(user_id, resource_type, resource_id)
        binding.status = BindingStatus.UNBOUND.value
        await self.repository.hard_delete(binding)
        await self.repository.commit()
        return {}
