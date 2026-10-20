"""Shared catalog metadata with separate, actor-owned authorization operations."""

from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from testing_agent.core.errors import AppError, ErrBadRequest, ErrNotFound
from testing_agent.core.sid import new_id
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.project import Project
from testing_agent.models.shared_service import ServiceAuthorization, SharedService
from testing_agent.repositories.deletion import delete_resource
from testing_agent.repositories.shared_service_catalog import SharedServiceCatalogRepository
from testing_agent.schemas.shared_service import McpTemplate
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.project_access import require_project_access
from testing_agent.services.service_instance import instance_key, normalize_instance_url
from testing_agent.services.shared_service_catalog import SharedServiceCatalog
from testing_agent.services.worker_authorization import revoke_executions
from testing_agent.services.zentao_mcp_identity import needs_instance_reset
from testing_agent.services.zentao_mcp_instance import discover_instance


class SharedServiceService:
    def __init__(self, connections: IntegrationConnectionService):
        self.connections = connections
        self.session = connections.repository.session

    async def project(self, user_id, project_id, action="read", *, lock=False):
        statement = select(Project).where(Project.project_id == project_id)
        if lock or action != "read":
            statement = statement.with_for_update().execution_options(populate_existing=True)
        project = await self.session.scalar(statement)
        if project is None:
            raise ErrNotFound()
        await require_project_access(self.session, user_id, project, action)

    async def get_resource(
        self, user_id, project_id, provider, service_id, action="read", *, lock=False
    ):
        await self.project(user_id, project_id, action, lock=lock)
        statement = select(SharedService).where(
            SharedService.service_id == service_id,
            SharedService.project_id == project_id,
            SharedService.provider == provider,
        )
        if lock or action != "read":
            statement = statement.with_for_update().execution_options(populate_existing=True)
        resource = await self.session.scalar(statement)
        if resource is None:
            raise ErrNotFound()
        return resource

    def catalog(self) -> SharedServiceCatalog:
        return SharedServiceCatalog(
            SharedServiceCatalogRepository(self.session),
            self.connections.credentials,
            discover=discover_instance,
            needs_reset=needs_instance_reset,
        )

    async def own_connection(self, resource, user_id):
        rows = await SharedServiceCatalogRepository(self.session).owned_connections(
            [resource], user_id
        )
        return rows.get(resource.service_id)

    async def dump(self, resource, user_id):
        return (await self.catalog().read([resource], user_id))[0]

    async def list(self, user_id, project_id, provider):
        await self.project(user_id, project_id)
        resources = await SharedServiceCatalogRepository(self.session).resources(
            project_id, provider
        )
        return {"items": await self.catalog().read(resources, user_id), "total": len(resources)}

    async def templates(self, user_id, project_id, provider):
        await self.project(user_id, project_id)
        if provider != "mcp":
            raise ErrNotFound()
        return {"items": [McpTemplate().model_dump(by_alias=True)], "total": 1}

    async def create(self, user_id, project_id, provider, body):
        await self.project(user_id, project_id, "manage")
        name = body.name.strip()
        model = body.model_id.strip()
        if not name or (provider == "llm" and not model) or (provider != "llm" and model):
            raise ErrBadRequest()
        if (provider == "mcp") != (body.template_id is not None):
            raise ErrBadRequest()
        base_url = normalize_instance_url(body.base_url)
        target_instance = self.normalize_zentao_instance(provider, body.zentao_instance_url)
        if provider == "mcp":
            # Legacy clients may send this field; it no longer controls identity.
            target_instance = ""
        if provider == "mcp":
            base_url = self.normalize_mcp_endpoint(body.base_url)
        resource = SharedService(
            service_id=new_id(),
            project_id=project_id,
            provider=provider,
            name=name,
            base_url=base_url,
            template_id=body.template_id,
            model_id=model,
            zentao_instance_url=target_instance,
        )
        self.session.add(resource)
        await self.commit_name()
        return await self.dump(resource, user_id)

    @staticmethod
    def normalize_mcp_endpoint(value):
        value = value.strip()
        normalize_instance_url(value)
        url = urlsplit(value)
        if (
            (url.port is not None and not 1 <= url.port <= 65535)
            or "?" in value
            or "#" in value
            or any(c.isspace() for c in value)
        ):
            raise ErrBadRequest()
        return value

    @staticmethod
    def normalize_zentao_instance(provider, value):
        if not value:
            return ""
        if provider != "mcp":
            raise ErrBadRequest()
        try:
            url = urlsplit(value.strip())
        except ValueError as exc:
            raise ErrBadRequest() from exc
        if url.query or url.fragment or any(c.isspace() for c in value.strip()):
            raise ErrBadRequest()
        return normalize_instance_url(value)

    async def rename(
        self,
        user_id,
        project_id,
        provider,
        service_id,
        name,
        zentao_instance_url=None,
        base_url=None,
        confirm_instance_switch=False,
    ):
        resource = await self.get_resource(user_id, project_id, provider, service_id, "manage")
        if not name.strip():
            raise ErrBadRequest()
        if zentao_instance_url is not None:
            self.normalize_zentao_instance(provider, zentao_instance_url)
        if confirm_instance_switch and provider != "mcp":
            raise ErrBadRequest()
        endpoint = resource.base_url
        if base_url is not None:
            if provider != "mcp":
                raise ErrBadRequest()
            endpoint = self.normalize_mcp_endpoint(base_url)
        if endpoint != resource.base_url and not confirm_instance_switch:
            raise AppError(400, "请勾选确认切换禅道并清除旧绑定后保存", 400)
        if confirm_instance_switch:
            original_endpoint = resource.base_url
            own = await self.own_connection(resource, user_id)
            if own is None or own.status != "active" or not (own.secret_json or {}).get("token"):
                raise AppError(400, "请先保存本人的 MCP Token，以核对新禅道目标", 400)
            token = self.connections.credentials.mcp_token(
                own, user_id=user_id, project_id=resource.project_id
            )
            await self.session.commit()  # Do not hold project locks during network requests.
            info = await discover_instance(endpoint, token)
            resource = await self.get_resource(user_id, project_id, provider, service_id, "manage")
            own = await self.own_connection(resource, user_id)
            if (
                resource.base_url != original_endpoint
                or own is None
                or own.status != "active"
                or not (own.secret_json or {}).get("token")
                or self.connections.credentials.mcp_token(
                    own, user_id=user_id, project_id=resource.project_id
                )
                != token
            ):
                raise AppError(409, "服务地址或本人授权已变更，请刷新后重新保存", 409)
            await self.accept_mcp_instance(resource, own, user_id, info)
        resource.base_url = endpoint
        # Instance identity is read from MCP, including for legacy catalog rows.
        resource.name = name.strip()
        connections = await self.session.scalars(
            select(IntegrationConnection)
            .join(
                ServiceAuthorization,
                ServiceAuthorization.connection_id == IntegrationConnection.connection_id,
            )
            .where(ServiceAuthorization.service_id == service_id)
        )
        for connection in connections:
            connection.extra_json = {**(connection.extra_json or {}), "serviceName": resource.name}
            if provider == "mcp":
                connection.base_url = resource.base_url
        await self.commit_name()
        return await self.dump(resource, user_id)

    async def commit_name(self):
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(409, "同类服务名称已存在，请使用其他名称", 409) from exc

    async def authorize(self, user_id, project_id, provider, service_id, body):
        resource = await self.get_resource(user_id, project_id, provider, service_id)
        credentials = body.model_dump(by_alias=True, exclude_none=True)
        required = {
            "mcp": {"token"},
            "llm": {"apiKey"},
            "gitlab": {"accessToken"},
            "zentao": {"account", "password"},
        }[provider]
        if set(credentials) != required or any(
            not str(value).strip() for value in credentials.values()
        ):
            raise ErrBadRequest()
        endpoint = resource.base_url
        info = None
        if provider == "mcp":
            try:
                info = await discover_instance(endpoint, credentials["token"])
            except AppError as exc:
                if exc.http_code != 502:
                    raise
        await self.session.commit()
        resource = await self.get_resource(user_id, project_id, provider, service_id, lock=True)
        if resource.base_url != endpoint:
            raise AppError(409, "服务地址已变更，请刷新后重新授权", 409)
        own = await self.own_connection(resource, user_id)
        if own is None:
            # A deleted old authorization is replaced; its encrypted history is not reassigned.
            old = await self.session.scalar(
                select(ServiceAuthorization).where(
                    ServiceAuthorization.service_id == service_id,
                    ServiceAuthorization.user_id == user_id,
                )
            )
            if old:
                await self.session.delete(old)
                await self.session.flush()
            result = await self.connections.create(
                provider,
                {
                    "name": f"authorization-{new_id()}",
                    "baseUrl": resource.base_url,
                    "modelId": resource.model_id,
                    **credentials,
                },
                user_id,
                project_id,
                commit=False,
            )
            own = await self.session.scalar(
                select(IntegrationConnection).where(
                    IntegrationConnection.connection_id == result["connectionId"]
                )
            )
            if own is None:
                raise ErrNotFound()
            self.session.add(
                ServiceAuthorization(
                    service_id=service_id, user_id=user_id, connection_id=own.connection_id
                )
            )
        else:
            await self.connections.update(
                provider, own.connection_id, credentials, user_id, project_id, commit=False
            )
        own.extra_json = {**(own.extra_json or {}), "serviceName": resource.name}
        own.status = "active"
        own.last_auth_at = datetime.now(UTC)
        if info is not None:
            # A newly supplied personal Token may be saved while an owner confirms
            # the target switch. Saving credentials never deletes project bindings.
            own.extra_json = {**own.extra_json, "zentaoAuthorizedInstance": info["instanceUrl"]}
            if not await needs_instance_reset(self.session, resource, info):
                resource.zentao_instance_url = info["instanceUrl"]
        await self.session.commit()
        return await self.dump(resource, user_id)

    async def reset_instance(self, user_id, project_id, provider, service_id, expected_instance):
        if provider != "mcp":
            raise ErrNotFound()
        expected_instance = normalize_instance_url(expected_instance)
        resource = await self.get_resource(user_id, project_id, provider, service_id, "manage")
        own = await self.own_connection(resource, user_id)
        if own is None or own.status != "active" or not (own.secret_json or {}).get("token"):
            raise AppError(400, "请先保存本人的 MCP Token，以核对新禅道目标", 400)
        endpoint = resource.base_url
        token = self.connections.credentials.mcp_token(
            own, user_id=user_id, project_id=resource.project_id
        )
        await self.session.commit()
        info = await discover_instance(endpoint, token)
        if instance_key(info["instanceUrl"]) != instance_key(expected_instance):
            raise AppError(409, "MCP 禅道目标已再次变化，请刷新后重新确认", 409)
        resource = await self.get_resource(user_id, project_id, provider, service_id, "manage")
        own = await self.own_connection(resource, user_id)
        if (
            resource.base_url != endpoint
            or own is None
            or own.status != "active"
            or not (own.secret_json or {}).get("token")
            or self.connections.credentials.mcp_token(
                own, user_id=user_id, project_id=resource.project_id
            )
            != token
        ):
            raise AppError(409, "服务地址或本人授权已变更，请刷新后重新确认", 409)
        if not await needs_instance_reset(self.session, resource, info):
            raise AppError(409, "禅道目标未变更，无需清除绑定", 409)
        await self.accept_mcp_instance(resource, own, user_id, info)
        await self.session.commit()
        return await self.dump(resource, user_id)

    async def accept_mcp_instance(self, resource, own, user_id, info):
        """Caller owns the project lock; endpoint and association updates commit together."""
        if await needs_instance_reset(self.session, resource, info):
            from testing_agent.services.zentao_mcp_authorization import invalidate_others
            from testing_agent.services.zentao_mcp_reset import clear_project_associations

            changed = not resource.zentao_instance_url or instance_key(
                resource.zentao_instance_url
            ) != instance_key(info["instanceUrl"])
            await clear_project_associations(
                self.session, resource.project_id, user_id, info["instanceUrl"], resource=resource
            )
            if changed:
                explicitly_authorized = (own.extra_json or {}).get("zentaoAuthorizedInstance")
                keep = own.connection_id if explicitly_authorized == info["instanceUrl"] else None
                await invalidate_others(self.session, resource.service_id, keep)
        resource.zentao_instance_url = info["instanceUrl"]

    async def revoke(self, user_id, project_id, provider, service_id):
        resource = await self.get_resource(user_id, project_id, provider, service_id, lock=True)
        own = await self.own_connection(resource, user_id)
        if own:
            await revoke_executions(self.session, actor=user_id, connection_id=own.connection_id)
            await delete_resource(self.session, own)
        await self.session.commit()
        return await self.dump(resource, user_id)

    async def delete(self, user_id, project_id, provider, service_id):
        resource = await self.get_resource(user_id, project_id, provider, service_id, "manage")
        connections = list(
            await self.session.scalars(
                select(IntegrationConnection)
                .join(
                    ServiceAuthorization,
                    ServiceAuthorization.connection_id == IntegrationConnection.connection_id,
                )
                .where(ServiceAuthorization.service_id == service_id)
            )
        )
        for own in connections:
            await revoke_executions(
                self.session, actor=own.user_id, connection_id=own.connection_id
            )
            await delete_resource(self.session, own)
        await delete_resource(self.session, resource)
        await self.session.commit()
        return {}
