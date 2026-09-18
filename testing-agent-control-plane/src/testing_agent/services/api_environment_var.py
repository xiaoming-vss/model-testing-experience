from __future__ import annotations

from typing import Any

from testing_agent.core.errors import ErrBadRequest, ErrForbidden, ErrNotFound
from testing_agent.core.sid import new_id
from testing_agent.models.api_environment import ApiEnvironment
from testing_agent.models.api_environment_var import ApiEnvironmentVar
from testing_agent.repositories.api_environment_var import ApiEnvironmentVarRepository
from testing_agent.schemas.api_environment_var import (
    ApiEnvironmentVarRequest,
    ApiEnvironmentVarResponse,
)
from testing_agent.services.common import apply_patch, dump, list_payload
from testing_agent.services.project_access import ProjectAction, require_project_access


class ApiEnvironmentVarService:
    def __init__(self, repository: ApiEnvironmentVarRepository):
        self.repository = repository

    async def get_accessible_environment(
        self, user_id: str, environment_id: str, *, action: ProjectAction = "read"
    ) -> ApiEnvironment:
        environment = await self.repository.get_environment(environment_id)
        if environment is None:
            raise ErrNotFound
        project = await self.repository.get_project(environment.project_id)
        if project is None:
            raise ErrNotFound
        await require_project_access(self.repository.session, user_id, project, action)
        return environment

    async def get_accessible_entity(
        self, user_id: str, env_var_id: str, *, action: ProjectAction = "read"
    ) -> ApiEnvironmentVar:
        var = await self.repository.get_var(env_var_id)
        if var is None:
            raise ErrNotFound
        await self.get_accessible_environment(user_id, var.environment_id, action=action)
        return var

    async def create(
        self, user_id: str, environment_id: str, body: ApiEnvironmentVarRequest
    ) -> dict:
        await self.get_accessible_environment(user_id, environment_id, action="write")
        var = ApiEnvironmentVar(
            env_var_id=new_id(),
            environment_id=environment_id,
            secret_user_id=user_id if body.is_secret else "",
            **body.model_dump(),
        )
        self.repository.add(var)
        await self.repository.commit()
        await self.repository.refresh(var)
        return dump(ApiEnvironmentVarResponse, var)

    async def list(self, user_id: str, environment_id: str) -> dict[str, Any]:
        await self.get_accessible_environment(user_id, environment_id, action="read")
        rows = await self.repository.list_by_environment(environment_id)
        return list_payload([dump(ApiEnvironmentVarResponse, row) for row in rows])

    async def get(self, user_id: str, env_var_id: str) -> dict:
        return dump(
            ApiEnvironmentVarResponse,
            await self.get_accessible_entity(user_id, env_var_id, action="read"),
        )

    async def update(self, user_id: str, env_var_id: str, body: dict[str, Any]) -> dict:
        var = await self.get_accessible_entity(user_id, env_var_id, action="write")
        body = dict(body)
        if var.is_secret:
            if var.secret_user_id != user_id:
                raise ErrForbidden
            if body.get("isSecret", body.get("is_secret")) is False:
                raise ErrBadRequest
            if body.get("value") == "********":
                body.pop("value")
        elif body.get("isSecret", body.get("is_secret")):
            var.secret_user_id = user_id
        apply_patch(var, body, {"var_key", "value", "description", "is_secret"})
        await self.repository.commit()
        await self.repository.refresh(var)
        return dump(ApiEnvironmentVarResponse, var)

    async def delete(self, user_id: str, env_var_id: str) -> dict:
        var = await self.get_accessible_entity(user_id, env_var_id, action="write")
        if var.is_secret and var.secret_user_id != user_id:
            raise ErrForbidden
        await self.repository.delete(var)
        await self.repository.commit()
        return {}
