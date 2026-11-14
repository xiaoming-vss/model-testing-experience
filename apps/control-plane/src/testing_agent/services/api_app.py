from __future__ import annotations

from http import HTTPStatus
from typing import Any

from sqlalchemy.exc import IntegrityError

from testing_agent.core.errors import (
    AppError,
    ErrApiAppHasInterfaces,
    ErrApiAppNameAlreadyUse,
    ErrApiAppNotFound,
    ErrApiAppRepositoryInvalid,
    ErrBadRequest,
    dynamic_error,
)
from testing_agent.core.sid import new_id
from testing_agent.domain.api_interface import normalize_base_path
from testing_agent.models.api_app import ApiApp
from testing_agent.repositories.api_app import ApiAppRepository
from testing_agent.repositories.resource_binding import ResourceBindingRepository
from testing_agent.schemas.api_app import (
    ApiAppCreateRequest,
    ApiAppRepositoryRequest,
    ApiAppResponse,
    ApiAppUpdateRequest,
)
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.project_access import ProjectAction, require_project_id
from testing_agent.services.resource_deletion import ResourceDeletion, SqlResourceDeletion
from testing_agent.services.service_instance import instance_key, normalize_instance_url


def dump_app(app: ApiApp) -> dict[str, Any]:
    repository = None
    if app.repository_project_id:
        repository = {
            "project_id": app.repository_project_id,
            "path": app.repository_path,
            "name": app.repository_name,
            "instance_url": app.repository_instance_url,
        }
    data = {
        "app_id": app.app_id,
        "project_id": app.project_id,
        "name": app.name,
        "description": app.description,
        "base_path": app.base_path,
        "repository": repository,
        "enabled": app.enabled,
        "interface_count": getattr(app, "interface_count", 0),
        "enabled_interface_count": getattr(app, "enabled_interface_count", 0),
        "version": app.version,
        "created_at": app.created_at,
        "updated_at": app.updated_at,
    }
    return ApiAppResponse.model_validate(data).model_dump(by_alias=True, mode="json")


class ApiAppService:
    def __init__(
        self,
        repository: ApiAppRepository,
        connections: IntegrationConnectionService | None = None,
        bindings: ResourceBindingRepository | None = None,
        *,
        deletion: ResourceDeletion | None = None,
    ) -> None:
        self.repository = repository
        self.connections = connections
        self.bindings = bindings or ResourceBindingRepository(repository.session)
        self.deletion = deletion or SqlResourceDeletion()

    async def list(self, user_id: str, project_id: str) -> dict[str, Any]:
        await require_project_id(self.repository.session, user_id, project_id, action="read")
        apps = await self.repository.list_by_project(project_id)
        return {"items": [dump_app(app) for app in apps], "total": len(apps)}

    async def get(self, user_id: str, app_id: str) -> dict[str, Any]:
        app = await self._accessible_app(user_id, app_id, action="read")
        await self._attach_counts(app)
        return dump_app(app)

    async def create(
        self, user_id: str, project_id: str, body: ApiAppCreateRequest
    ) -> dict[str, Any]:
        await require_project_id(self.repository.session, user_id, project_id, action="manage")
        name = self._name(body.name)
        description = body.description.strip()
        base_path = self._base_path(body.base_path)
        repository = await self._repository_values(user_id, project_id, body.repository)
        if await self.repository.get_by_project_and_name(project_id, name) is not None:
            raise ErrApiAppNameAlreadyUse()
        app = ApiApp(
            app_id=new_id(),
            project_id=project_id,
            name=name,
            description=description,
            base_path=base_path,
            enabled=body.enabled,
            version=1,
            created_by_user_id=user_id,
            **repository,
        )
        self.repository.add(app)
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ErrApiAppNameAlreadyUse() from exc
        await self.repository.refresh(app)
        await self._attach_counts(app)
        return dump_app(app)

    async def update(self, user_id: str, app_id: str, body: ApiAppUpdateRequest) -> dict[str, Any]:
        app = await self._accessible_app(user_id, app_id, action="manage", for_update=True)
        fields = body.model_fields_set
        changed = False
        if "name" in fields:
            if body.name is None:
                raise ErrBadRequest()
            name = self._name(body.name)
            if name != app.name:
                if (
                    await self.repository.get_by_project_and_name(
                        app.project_id, name, exclude_app_id=app.app_id
                    )
                    is not None
                ):
                    raise ErrApiAppNameAlreadyUse()
                app.name = name
                changed = True
        if "description" in fields:
            if body.description is None:
                raise ErrBadRequest()
            description = body.description.strip()
            if description != app.description:
                app.description = description
                changed = True
        if "base_path" in fields:
            if body.base_path is None:
                raise ErrBadRequest()
            base_path = self._base_path(body.base_path)
            if base_path != app.base_path:
                app.base_path = base_path
                changed = True
        if "repository" in fields:
            repository = await self._repository_values(user_id, app.project_id, body.repository)
            if any(getattr(app, key) != value for key, value in repository.items()):
                for key, value in repository.items():
                    setattr(app, key, value)
                changed = True
        if "enabled" in fields:
            if body.enabled is None:
                raise ErrBadRequest()
            if body.enabled != app.enabled:
                app.enabled = body.enabled
                changed = True
        if changed:
            app.version += 1
            try:
                await self.repository.commit()
            except IntegrityError as exc:
                await self.repository.rollback()
                raise ErrApiAppNameAlreadyUse() from exc
            await self.repository.refresh(app)
        await self._attach_counts(app)
        return dump_app(app)

    async def delete(self, user_id: str, app_id: str) -> dict[str, Any]:
        app = await self.repository.get_for_update(app_id)
        if app is None:
            raise ErrApiAppNotFound()
        await require_project_id(self.repository.session, user_id, app.project_id, action="manage")
        if await self.repository.count_interfaces(app_id) > 0:
            raise ErrApiAppHasInterfaces()
        await self.deletion.delete(self.repository.session, app)
        await self.repository.commit()
        return {}

    async def _accessible_app(
        self,
        user_id: str,
        app_id: str,
        *,
        action: ProjectAction,
        for_update: bool = False,
    ) -> ApiApp:
        app = (
            await self.repository.get_for_update(app_id)
            if for_update
            else await self.repository.get(app_id)
        )
        if app is None:
            raise ErrApiAppNotFound()
        await require_project_id(self.repository.session, user_id, app.project_id, action=action)
        return app

    async def _attach_counts(self, app: ApiApp) -> None:
        app.interface_count = await self.repository.count_interfaces(app.app_id)
        app.enabled_interface_count = await self.repository.count_interfaces(
            app.app_id, enabled=True
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
        repository: ApiAppRepositoryRequest | None,
    ) -> dict[str, str]:
        if repository is None:
            return {
                "repository_project_id": "",
                "repository_path": "",
                "repository_name": "",
                "repository_instance_url": "",
            }
        if self.connections is None:
            raise ErrApiAppRepositoryInvalid()
        try:
            connection = await self.connections.get_active_personal(
                user_id, "gitlab", repository.connection_id, project_id
            )
            binding = await self.bindings.get_active_project_group_binding(
                "gitlab",
                project_id,
                repository.group_id,
                instance=instance_key(connection.base_url),
            )
            if binding is None:
                raise ErrApiAppRepositoryInvalid()
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
            # Re-lock the group binding after the remote calls. A concurrent unbind either
            # waits for this write or removes the binding first and makes this request fail.
            locked = await self.bindings.get_active_project_group_binding(
                "gitlab",
                project_id,
                repository.group_id,
                for_update=True,
                instance=instance_key(connection.base_url),
            )
            if locked is None:
                raise ErrApiAppRepositoryInvalid()
        except AppError as exc:
            if exc.http_code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
                raise
            raise dynamic_error(ErrApiAppRepositoryInvalid, exc.message) from exc
        path = str(project.get("pathWithNamespace") or "").strip()
        if not path:
            raise ErrApiAppRepositoryInvalid()
        return {
            "repository_project_id": canonical_id,
            "repository_path": path,
            "repository_name": path.rsplit("/", 1)[-1],
            "repository_instance_url": normalize_instance_url(connection.base_url),
        }


__all__ = ["ApiAppService", "dump_app"]
