from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from testing_agent.core.enums import BindingStatus
from testing_agent.core.errors import (
    AppError,
    ErrBadRequest,
    ErrIntegrationConnectionNotFound,
    ErrNotFound,
    ErrRemoteResourceAlreadyBound,
    ErrResourceBindingAlreadyExists,
    ErrResourceBindingInvalid,
    ErrZentaoRemoteResourceUnavailable,
    dynamic_error,
)
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.repositories.resource_binding import ResourceBindingRepository
from testing_agent.services.binding_support import LocalBindingAccess, commit_binding, dump_binding
from testing_agent.services.integration_connection import IntegrationConnectionService, item_value
from testing_agent.services.project_access import require_project_access
from testing_agent.services.service_instance import instance_key, normalize_instance_url
from testing_agent.services.zentao_mcp import ZentaoMcpAccess
from testing_agent.services.zentao_mcp_selection import binding_service_id, inherited_mcp_service_id
from testing_agent.services.zentao_resource import parse_zentao_remote_id, truncate_error

ZENTAO_REMOTE_TYPE_DEFAULTS = {"project": "project", "sprint": "execution", "requirement": "story"}


class ZentaoBindings:
    def __init__(
        self,
        repository: ResourceBindingRepository,
        connections: IntegrationConnectionService | None,
        *,
        authorize: LocalBindingAccess,
        id_factory: Callable[[], str],
        client: Any | None = None,
        access: Any | None = None,
    ) -> None:
        self.repository = repository
        self.integration_connection_service = connections
        self.authorize = authorize
        self.new_id = id_factory
        self.zentao_resource_client = client
        self.zentao_access = access

    async def _resolve_zentao(self, user_id, project_id, expected_instance="", mcp_service_id=""):
        access = self.zentao_access or ZentaoMcpAccess(self.integration_connection_service)
        if mcp_service_id:
            return await access.resolve(
                user_id, project_id, expected_instance, mcp_service_id=mcp_service_id
            )
        return await access.resolve(user_id, project_id, expected_instance)

    async def create(
        self, resource_type: str, resource_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        if resource_type == "project":
            return await self._create_project(resource_id, body, user_id)

        project_id = await self.authorize(user_id, resource_type, resource_id)
        service = self.integration_connection_service
        if service is None or self.zentao_resource_client is None:
            raise ErrIntegrationConnectionNotFound()
        if await self.repository.get_active_by_local_resource(resource_type, resource_id):
            raise ErrResourceBindingAlreadyExists()
        if resource_type == "sprint":
            parent = await self.repository.get_active_by_local_resource("project", project_id)
        else:
            requirement = await self.repository.get_requirement(resource_id)
            if requirement is None:
                raise ErrNotFound()
            parent = await self.repository.get_active_by_local_resource(
                "sprint", requirement.sprint_id
            )
        if parent is None or parent.provider != "zentao":
            raise ErrResourceBindingInvalid()
        connection = await self._resolve_zentao(
            user_id,
            project_id,
            parent.instance_url,
            await inherited_mcp_service_id(
                self.repository.session, project_id, str(body.get("mcpServiceId") or "")
            ),
        )
        connection_id = connection.connection_id
        if binding_service_id(parent) and getattr(
            connection, "service_id", ""
        ) != binding_service_id(parent):
            raise AppError(400, "下级绑定须使用上级绑定的禅道 MCP", 400)
        if parent.instance_key != instance_key(connection.base_url):
            raise ErrResourceBindingInvalid()
        try:
            remote_id = str(parse_zentao_remote_id(str(body.get("remoteResourceId") or "")))
        except ValueError as exc:
            raise dynamic_error(ErrResourceBindingInvalid, str(exc)) from exc
        requested_parent = str(body.get("remoteParentId") or "")
        if requested_parent and requested_parent != parent.remote_resource_id:
            raise ErrResourceBindingInvalid()
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
                matched = next(item for item in items if str(item_value(item, "id")) == remote_id)
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
            raise ErrResourceBindingInvalid()
        body = {**body, "remoteResourceId": remote_id, "remoteParentId": parent.remote_resource_id}
        binding = ResourceBinding(
            binding_id=self.new_id(),
            user_id=user_id,
            provider="zentao",
            connection_id=connection_id,
            instance_url=normalize_instance_url(connection.base_url),
            instance_key=instance_key(connection.base_url),
            local_resource_type=resource_type,
            local_resource_id=resource_id,
            remote_resource_type=ZENTAO_REMOTE_TYPE_DEFAULTS[resource_type],
            remote_resource_id=str(
                body.get("remoteResourceId") or body.get("remote_resource_id") or ""
            ),
            remote_parent_id=str(body.get("remoteParentId") or body.get("remote_parent_id") or ""),
            remote_name_snapshot=str(item_value(matched, "name", "title")),
            status=BindingStatus.ACTIVE.value,
            bound_at=datetime.now(UTC),
            extra_json={
                **(body.get("extraJson") or body.get("extra_json") or {}),
                **(
                    {"mcpServiceId": connection.service_id}
                    if getattr(connection, "service_id", "")
                    else {}
                ),
            },
        )
        self.repository.add(binding)
        await commit_binding(self.repository)
        await self.repository.refresh(binding)
        return dump_binding(binding)

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

        provider = "zentao"
        connection_id = str(body.get("connectionId") or body.get("connection_id") or "").strip()
        remote_resource_id = str(
            body.get("remoteResourceId") or body.get("remote_resource_id") or ""
        ).strip()
        if not remote_resource_id:
            raise ErrBadRequest()
        try:
            parse_zentao_remote_id(remote_resource_id)
        except ValueError as exc:
            raise dynamic_error(ErrResourceBindingInvalid, str(exc)) from exc

        if self.integration_connection_service is None:
            raise ErrIntegrationConnectionNotFound()
        connection = await self._resolve_zentao(
            user_id, project_id, mcp_service_id=str(body.get("mcpServiceId") or "")
        )
        connection_id = connection.connection_id

        existing_local = await self.repository.get_active_by_local_resource("project", project_id)
        if existing_local is not None:
            raise ErrResourceBindingAlreadyExists()

        if self.zentao_resource_client is None:
            raise ErrZentaoRemoteResourceUnavailable()
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
            instance=instance_key(connection.base_url),
        )
        if remote_exists:
            raise ErrRemoteResourceAlreadyBound()

        now = datetime.now(UTC)
        binding = ResourceBinding(
            binding_id=self.new_id(),
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
            extra_json={"mcpServiceId": connection.service_id}
            if getattr(connection, "service_id", "")
            else {},
        )
        self.repository.add(binding)
        await commit_binding(self.repository)
        await self.repository.refresh(binding)
        return dump_binding(binding)

    async def update(
        self, binding: ResourceBinding, body: dict[str, Any], user_id: str
    ) -> dict[str, Any]:
        project_id = await self.authorize(
            user_id, binding.local_resource_type, binding.local_resource_id
        )
        if self.integration_connection_service is None or self.zentao_resource_client is None:
            raise ErrIntegrationConnectionNotFound()
        chosen_id = str(body.get("mcpServiceId") or binding_service_id(binding))
        if binding.local_resource_type != "project":
            chosen_id = await inherited_mcp_service_id(
                self.repository.session, project_id, str(body.get("mcpServiceId") or "")
            )
        expected = (
            ""
            if binding.local_resource_type == "project" and body.get("mcpServiceId")
            else binding.instance_url
        )
        connection = await self._resolve_zentao(user_id, project_id, expected, chosen_id)
        remote_id = str(body.get("remoteResourceId") or binding.remote_resource_id)
        try:
            remote_id = str(parse_zentao_remote_id(remote_id))
        except ValueError as exc:
            raise ErrResourceBindingInvalid() from exc
        if binding.instance_key != instance_key(connection.base_url):
            if binding.local_resource_type != "project" or not body.get("confirmInstanceSwitch"):
                raise AppError(400, "更换禅道实例时请勾选确认清除旧关联后重新绑定", 400)
            remote = await self.zentao_resource_client.get_project(connection, remote_id)
            if item_value(remote, "deleted", default=False):
                raise ErrResourceBindingInvalid()
            from testing_agent.services.zentao_mcp_reset import clear_project_associations

            await clear_project_associations(
                self.repository.session, project_id, user_id, connection.base_url
            )
            return await self._create_project(project_id, body, user_id)
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
                raise ErrResourceBindingInvalid()
        if binding.local_resource_type == "project":
            if (
                remote_id != binding.remote_resource_id
                and await self.repository.exists_active_by_remote_resource(
                    "zentao",
                    connection.connection_id,
                    "project",
                    remote_id,
                    instance=instance_key(connection.base_url),
                )
            ):
                raise ErrRemoteResourceAlreadyBound()
            remote = await self.zentao_resource_client.get_project(connection, remote_id)
            if item_value(remote, "deleted", default=False):
                raise ErrResourceBindingInvalid()
        else:
            if binding.local_resource_type == "sprint":
                parent = await self.repository.get_active_by_local_resource("project", project_id)
            else:
                requirement = await self.repository.get_requirement(binding.local_resource_id)
                if requirement is None:
                    raise ErrNotFound()
                parent = await self.repository.get_active_by_local_resource(
                    "sprint", requirement.sprint_id
                )
            if (
                parent is None
                or parent.provider != "zentao"
                or parent.instance_key != binding.instance_key
            ):
                raise ErrResourceBindingInvalid()
            if binding_service_id(parent) and getattr(
                connection, "service_id", ""
            ) != binding_service_id(parent):
                raise AppError(400, "下级绑定须使用上级绑定的禅道 MCP", 400)
            try:
                parent_id = str(parse_zentao_remote_id(parent.remote_resource_id))
            except ValueError as exc:
                raise ErrResourceBindingInvalid() from exc
            if binding.remote_parent_id and binding.remote_parent_id != parent_id:
                raise ErrResourceBindingInvalid()
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
                    remote = next(
                        item for item in items if str(item_value(item, "id")) == remote_id
                    )
                    break
                if (
                    binding.local_resource_type != "sprint"
                    or not items
                    or page * 100 >= int(result.get("total") or len(items))
                ):
                    raise ErrResourceBindingInvalid()
                page += 1
            binding.remote_parent_id = parent_id
        if binding.remote_resource_id != remote_id:
            from testing_agent.services.integration_lifecycle import change_target

            await change_target(self.repository.session, project_id=project_id)
        if (
            binding.local_resource_type == "project"
            and bool(getattr(connection, "service_id", ""))
            and binding_service_id(binding) != connection.service_id
        ):
            await self._inherit_project_mcp(project_id, connection)
        binding.remote_resource_id = remote_id
        binding.remote_name_snapshot = str(item_value(remote, "name", "title"))
        if getattr(connection, "service_id", ""):
            binding.extra_json = {
                **(binding.extra_json or {}),
                "mcpServiceId": connection.service_id,
            }
        binding.last_verified_at = datetime.now(UTC)
        await commit_binding(self.repository)
        await self.repository.refresh(binding)
        return dump_binding(binding)

    async def _inherit_project_mcp(self, project_id, connection):
        # Same-instance transport changes preserve remote IDs and use the new service.
        from testing_agent.models.bug import Bug
        from testing_agent.models.bug_zentao_push import BugZentaoPush
        from testing_agent.services.integration_lifecycle import change_target
        from testing_agent.services.zentao_mcp_identity import project_binding_scope

        await change_target(self.repository.session, project_id=project_id)

        rows = await self.repository.session.scalars(
            select(ResourceBinding).where(project_binding_scope(project_id))
        )
        for child_binding in rows:
            child_binding.extra_json = {
                **(child_binding.extra_json or {}),
                "mcpServiceId": connection.service_id,
            }
        pushes = list(
            await self.repository.session.scalars(
                select(BugZentaoPush).where(
                    BugZentaoPush.bug_id.in_(select(Bug.bug_id).where(Bug.project_id == project_id))
                )
            )
        )
        if any(push.status in {"preparing", "creating", "unknown"} for push in pushes):
            raise AppError(409, "存在进行中或结果待确认的禅道推送，请处理后更换 MCP", 409)
        from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment

        active_attachment = await self.repository.session.scalar(
            select(BugZentaoAttachment.id)
            .join(Bug, Bug.bug_id == BugZentaoAttachment.bug_id)
            .where(
                Bug.project_id == project_id,
                BugZentaoAttachment.status.in_(["pending", "uploading"]),
                BugZentaoAttachment.updated_at >= datetime.now(UTC) - timedelta(minutes=6),
            )
            .limit(1)
        )
        if active_attachment is not None:
            raise AppError(409, "附件正在同步，请完成后更换 MCP", 409)
        for push in pushes:
            if instance_key(push.instance_url) == instance_key(connection.base_url):
                push.service_id = connection.service_id
