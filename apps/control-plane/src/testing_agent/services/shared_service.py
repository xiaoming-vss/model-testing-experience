"""Shared catalog metadata with separate, actor-owned authorization operations."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from testing_agent.core.errors import AppError, ErrBadRequest, ErrNotFound
from testing_agent.core.sid import new_id
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.project import Project
from testing_agent.models.shared_service import ServiceAuthorization, SharedService
from testing_agent.repositories.deletion import delete_resource
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.project_access import require_project_access
from testing_agent.services.service_instance import normalize_instance_url
from testing_agent.services.worker_authorization import revoke_executions


class SharedServiceService:
    def __init__(self, connections: IntegrationConnectionService):
        self.connections = connections
        self.session = connections.repository.session

    async def project(self, user_id, project_id, action="read"):
        project = await self.session.scalar(
            select(Project).where(Project.project_id == project_id).with_for_update()
        )
        if project is None:
            raise ErrNotFound
        await require_project_access(self.session, user_id, project, action)

    async def get_resource(self, user_id, project_id, provider, service_id, action="read"):
        await self.project(user_id, project_id, action)
        resource = await self.session.scalar(
            select(SharedService)
            .where(
                SharedService.service_id == service_id,
                SharedService.project_id == project_id,
                SharedService.provider == provider,
            )
            .with_for_update()
        )
        if resource is None:
            raise ErrNotFound
        return resource

    async def own_connection(self, resource, user_id):
        return await self.session.scalar(
            select(IntegrationConnection)
            .join(
                ServiceAuthorization,
                ServiceAuthorization.connection_id == IntegrationConnection.connection_id,
            )
            .where(
                ServiceAuthorization.service_id == resource.service_id,
                ServiceAuthorization.user_id == user_id,
                IntegrationConnection.user_id == user_id,
            )
        )

    async def dump(self, resource, user_id):
        own = await self.own_connection(resource, user_id)
        authorization = {"status": "unauthorized"}
        if own is not None:
            authorization = {
                "status": "authorized" if own.status == "active" else "invalid",
                "connectionId": own.connection_id,
                "account": own.account,
                "lastAuthAt": own.last_auth_at,
            }
        return {
            "serviceId": resource.service_id,
            "projectId": resource.project_id,
            "provider": resource.provider,
            "name": resource.name,
            "baseUrl": resource.base_url,
            "modelId": resource.model_id,
            "authorization": authorization,
        }

    async def list(self, user_id, project_id, provider):
        await self.project(user_id, project_id)
        resources = list(
            await self.session.scalars(
                select(SharedService)
                .where(
                    SharedService.project_id == project_id,
                    SharedService.provider == provider,
                )
                .order_by(SharedService.created_at.desc())
            )
        )
        return {
            "items": [await self.dump(row, user_id) for row in resources],
            "total": len(resources),
        }

    async def create(self, user_id, project_id, provider, body):
        await self.project(user_id, project_id, "manage")
        name = body.name.strip()
        model = body.model_id.strip()
        if not name or (provider == "llm" and not model) or (provider != "llm" and model):
            raise ErrBadRequest
        resource = SharedService(
            service_id=new_id(),
            project_id=project_id,
            provider=provider,
            name=name,
            base_url=normalize_instance_url(body.base_url),
            model_id=model,
        )
        self.session.add(resource)
        await self.commit_name()
        return await self.dump(resource, user_id)

    async def rename(self, user_id, project_id, provider, service_id, name):
        resource = await self.get_resource(user_id, project_id, provider, service_id, "manage")
        if not name.strip():
            raise ErrBadRequest
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
            "llm": {"apiKey"},
            "gitlab": {"accessToken"},
            "zentao": {"account", "password"},
        }[provider]
        if set(credentials) != required or any(
            not str(value).strip() for value in credentials.values()
        ):
            raise ErrBadRequest
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
        await self.session.commit()
        return await self.dump(resource, user_id)

    async def revoke(self, user_id, project_id, provider, service_id):
        resource = await self.get_resource(user_id, project_id, provider, service_id)
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
