from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError

from testing_agent.core.errors import (
    ErrApiAppNotFound,
    ErrApiInterfaceIdentityAlreadyUse,
    ErrApiInterfaceNotFound,
    ErrApiInterfacePathParamsMismatch,
    ErrApiInterfaceRequirementMismatch,
    ErrBadRequest,
    dynamic_error,
)
from testing_agent.core.sid import new_id
from testing_agent.domain.api_interface import (
    normalize_method,
    normalize_path,
    normalize_rows,
    normalize_tags,
    parse_json_value,
    path_key,
    validate_path_parameters,
)
from testing_agent.domain.api_interface_query import ApiInterfaceQuery
from testing_agent.models.api_app import ApiApp
from testing_agent.models.api_interface import ApiInterface
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.repositories.api_app import ApiAppRepository
from testing_agent.repositories.api_interface import ApiInterfaceRepository
from testing_agent.schemas.api_interface import (
    ApiInterfaceCreateRequest,
    ApiInterfaceListItem,
    ApiInterfaceResponse,
    ApiInterfaceRow,
    ApiInterfaceUpdateRequest,
)
from testing_agent.services.project_access import ProjectAction, require_project_id
from testing_agent.services.resource_deletion import ResourceDeletion, SqlResourceDeletion


def _requirement_rows(interface: ApiInterface) -> list[dict[str, str]]:
    return list(getattr(interface, "requirements", []) or [])


def dump_interface(interface: ApiInterface, *, app_name: str = "") -> dict[str, Any]:
    data = {
        "interface_id": interface.interface_id,
        "app_id": interface.app_id,
        "app_name": app_name or getattr(interface, "app_name", ""),
        "name": interface.name,
        "method": interface.method,
        "path": interface.path,
        "description": interface.description,
        "tags": interface.tags_json or [],
        "headers": interface.headers_json or [],
        "path_params": interface.path_params_json or [],
        "query_params": interface.query_params_json or [],
        "body_type": interface.body_type,
        "body_schema": interface.body_schema_json,
        "body_example": interface.body_example_json,
        "body_text": interface.body_text,
        "response_status": interface.response_status,
        "response_description": interface.response_description,
        "response_schema": interface.response_schema_json,
        "response_example": interface.response_example_json,
        "enabled": interface.enabled,
        "version": interface.version,
        "requirements": _requirement_rows(interface),
        "source": {
            "type": interface.source_type,
            "name": interface.source_name,
            "url": interface.source_url,
            "version": interface.source_version,
            "imported_at": interface.source_imported_at,
        },
        "created_at": interface.created_at,
        "updated_at": interface.updated_at,
    }
    return ApiInterfaceResponse.model_validate(data).model_dump(by_alias=True, mode="json")


def dump_list_item(interface: ApiInterface) -> dict[str, Any]:
    data = {
        "interface_id": interface.interface_id,
        "app_id": interface.app_id,
        "app_name": getattr(interface, "app_name", ""),
        "name": interface.name,
        "method": interface.method,
        "path": interface.path,
        "description": interface.description,
        "tags": interface.tags_json or [],
        "requirements": _requirement_rows(interface),
        "enabled": interface.enabled,
        "source_type": interface.source_type,
        "updated_at": interface.updated_at,
    }
    return ApiInterfaceListItem.model_validate(data).model_dump(by_alias=True, mode="json")


class ApiInterfaceService:
    def __init__(
        self,
        repository: ApiInterfaceRepository,
        apps: ApiAppRepository,
        *,
        deletion: ResourceDeletion | None = None,
    ) -> None:
        self.repository = repository
        self.apps = apps
        self.deletion = deletion or SqlResourceDeletion()

    async def list_project(self, user_id: str, query: ApiInterfaceQuery) -> dict[str, Any]:
        await require_project_id(self.repository.session, user_id, query.project_id, action="read")
        interfaces, total = await self.repository.list_by_project(query)
        return {
            "items": [dump_list_item(interface) for interface in interfaces],
            "total": total,
        }

    async def list_app(self, user_id: str, app_id: str, query: ApiInterfaceQuery) -> dict[str, Any]:
        app = await self._accessible_app(user_id, app_id, action="read")
        interfaces, total = await self.repository.list_by_app(app.app_id, query)
        return {
            "items": [dump_list_item(interface) for interface in interfaces],
            "total": total,
        }

    async def get(self, user_id: str, interface_id: str) -> dict[str, Any]:
        interface, app = await self._accessible_interface(user_id, interface_id, action="read")
        await self.repository.attach_requirements([interface])
        return dump_interface(interface, app_name=app.name)

    async def create(
        self, user_id: str, app_id: str, body: ApiInterfaceCreateRequest
    ) -> dict[str, Any]:
        # Lock the app so a concurrent app deletion cannot pass its interface count check
        # between the ownership check and the insert below.
        app = await self._accessible_app(user_id, app_id, action="write", for_update=True)
        payload = self._create_payload(body)
        if (
            await self.repository.get_by_identity(app_id, payload["method"], payload["path_key"])
            is not None
        ):
            raise ErrApiInterfaceIdentityAlreadyUse()
        requirements = await self._requirements(app.project_id, body.requirement_ids)
        interface = ApiInterface(
            interface_id=new_id(),
            app_id=app_id,
            enabled=body.enabled,
            version=1,
            source_type="manual",
            source_name="",
            source_url="",
            source_version="",
            source_imported_at=None,
            **payload,
        )
        self.repository.add(interface)
        try:
            await self.repository.flush()
            await self.repository.replace_requirements(interface.interface_id, requirements)
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ErrApiInterfaceIdentityAlreadyUse() from exc
        await self.repository.refresh(interface)
        await self.repository.attach_requirements([interface])
        return dump_interface(interface, app_name=app.name)

    async def update(
        self, user_id: str, interface_id: str, body: ApiInterfaceUpdateRequest
    ) -> dict[str, Any]:
        interface, app = await self._accessible_interface(
            user_id, interface_id, action="write", for_update=True
        )
        await self.repository.attach_requirements([interface])
        fields = body.model_fields_set
        changed = False

        name = interface.name
        if "name" in fields:
            if body.name is None:
                raise ErrBadRequest()
            name = self._text(body.name, "接口名称", 120)

        method = interface.method
        if "method" in fields:
            if body.method is None:
                raise ErrBadRequest()
            method = self._method(body.method)
        path = interface.path
        if "path" in fields:
            if body.path is None:
                raise ErrBadRequest()
            path = self._path(body.path)
        if "path_params" in fields:
            if body.path_params is None:
                raise ErrBadRequest()
            path_rows = self._rows(body.path_params, "path")
        else:
            path_rows = list(interface.path_params_json or [])
        if "path" in fields or "path_params" in fields:
            try:
                validate_path_parameters(path, path_rows)
            except ValueError as exc:
                raise dynamic_error(ErrApiInterfacePathParamsMismatch, str(exc)) from exc
        if method != interface.method or path != interface.path:
            new_path_key = path_key(path)
            exists = await self.repository.get_by_identity(interface.app_id, method, new_path_key)
            if exists is not None and exists.interface_id != interface.interface_id:
                raise ErrApiInterfaceIdentityAlreadyUse()
            interface.method = method
            interface.path = path
            interface.path_key = new_path_key
            changed = True
        if "path_params" in fields:
            interface.path_params_json = path_rows
            changed = True
        if "name" in fields and name != interface.name:
            interface.name = name
            changed = True
        if "description" in fields:
            if body.description is None:
                raise ErrBadRequest()
            description = body.description.strip()
            if description != interface.description:
                interface.description = description
                changed = True
        if "tags" in fields:
            if body.tags is None:
                raise ErrBadRequest()
            tags = self._tags(body.tags)
            if tags != (interface.tags_json or []):
                interface.tags_json = tags
                changed = True
        if "headers" in fields:
            if body.headers is None:
                raise ErrBadRequest()
            headers = self._rows(body.headers, "header")
            if headers != (interface.headers_json or []):
                interface.headers_json = headers
                changed = True
        if "query_params" in fields:
            if body.query_params is None:
                raise ErrBadRequest()
            query_params = self._rows(body.query_params, "query")
            if query_params != (interface.query_params_json or []):
                interface.query_params_json = query_params
                changed = True
        if "body_type" in fields:
            if body.body_type is None:
                raise ErrBadRequest()
            if body.body_type != interface.body_type:
                interface.body_type = body.body_type
                changed = True
        if "body_schema" in fields:
            value = self._json_value(body.body_schema)
            if value != interface.body_schema_json:
                interface.body_schema_json = value
                changed = True
        if "body_example" in fields:
            value = self._json_value(body.body_example)
            if value != interface.body_example_json:
                interface.body_example_json = value
                changed = True
        if "body_text" in fields:
            if body.body_text is None:
                raise ErrBadRequest()
            if body.body_text != interface.body_text:
                interface.body_text = body.body_text
                changed = True
        if "response_status" in fields:
            if body.response_status is None:
                raise ErrBadRequest()
            if body.response_status != interface.response_status:
                interface.response_status = body.response_status
                changed = True
        if "response_description" in fields:
            if body.response_description is None:
                raise ErrBadRequest()
            description = body.response_description.strip()
            if description != interface.response_description:
                interface.response_description = description
                changed = True
        if "response_schema" in fields:
            value = self._json_value(body.response_schema)
            if value != interface.response_schema_json:
                interface.response_schema_json = value
                changed = True
        if "response_example" in fields:
            value = self._json_value(body.response_example)
            if value != interface.response_example_json:
                interface.response_example_json = value
                changed = True
        if "enabled" in fields:
            if body.enabled is None:
                raise ErrBadRequest()
            if body.enabled != interface.enabled:
                interface.enabled = body.enabled
                changed = True
        if "requirement_ids" in fields:
            if body.requirement_ids is None:
                raise ErrBadRequest()
            requirements = await self._requirements(app.project_id, body.requirement_ids)
            current_ids = [row["requirement_id"] for row in _requirement_rows(interface)]
            next_ids = [requirement.requirement_id for requirement, _sprint in requirements]
            if set(current_ids) != set(next_ids):
                await self.repository.replace_requirements(interface.interface_id, requirements)
                changed = True
        if changed:
            interface.version += 1
            try:
                await self.repository.commit()
            except IntegrityError as exc:
                await self.repository.rollback()
                raise ErrApiInterfaceIdentityAlreadyUse() from exc
            await self.repository.refresh(interface)
        await self.repository.attach_requirements([interface])
        return dump_interface(interface, app_name=app.name)

    async def delete(self, user_id: str, interface_id: str) -> dict[str, Any]:
        interface, _app = await self._accessible_interface(
            user_id, interface_id, action="write", for_update=True
        )
        await self.repository.delete_requirements(interface_id)
        await self.deletion.delete(self.repository.session, interface)
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
        app = await self.apps.get_for_update(app_id) if for_update else await self.apps.get(app_id)
        if app is None:
            raise ErrApiAppNotFound()
        await require_project_id(self.repository.session, user_id, app.project_id, action=action)
        return app

    async def _accessible_interface(
        self,
        user_id: str,
        interface_id: str,
        *,
        action: ProjectAction,
        for_update: bool = False,
    ) -> tuple[ApiInterface, ApiApp]:
        interface = (
            await self.repository.get_for_update(interface_id)
            if for_update
            else await self.repository.get(interface_id)
        )
        if interface is None:
            raise ErrApiInterfaceNotFound()
        app = await self.apps.get(interface.app_id)
        if app is None:
            raise ErrApiInterfaceNotFound()
        await require_project_id(self.repository.session, user_id, app.project_id, action=action)
        return interface, app

    async def _requirements(
        self, project_id: str, requirement_ids: list[str]
    ) -> list[tuple[Requirement, Sprint]]:
        ids = list(dict.fromkeys(str(value).strip() for value in requirement_ids if value))
        rows = await self.repository.requirements_by_ids(project_id, ids)
        if len(rows) != len(ids):
            raise ErrApiInterfaceRequirementMismatch()
        return rows

    def _create_payload(self, body: ApiInterfaceCreateRequest) -> dict[str, Any]:
        method = self._method(body.method)
        path = self._path(body.path)
        path_params = self._rows(body.path_params, "path")
        try:
            validate_path_parameters(path, path_params)
        except ValueError as exc:
            raise dynamic_error(ErrApiInterfacePathParamsMismatch, str(exc)) from exc
        return {
            "name": self._text(body.name, "接口名称", 120),
            "method": method,
            "path": path,
            "path_key": path_key(path),
            "description": body.description.strip(),
            "tags_json": self._tags(body.tags),
            "headers_json": self._rows(body.headers, "header"),
            "path_params_json": path_params,
            "query_params_json": self._rows(body.query_params, "query"),
            "body_type": body.body_type,
            "body_schema_json": self._json_value(body.body_schema),
            "body_example_json": self._json_value(body.body_example),
            "body_text": body.body_text,
            "response_status": body.response_status,
            "response_description": body.response_description.strip(),
            "response_schema_json": self._json_value(body.response_schema),
            "response_example_json": self._json_value(body.response_example),
        }

    def _method(self, value: str) -> str:
        try:
            return normalize_method(value)
        except ValueError as exc:
            raise dynamic_error(ErrBadRequest, str(exc)) from exc

    def _path(self, value: str) -> str:
        try:
            return normalize_path(value)
        except ValueError as exc:
            raise dynamic_error(ErrBadRequest, str(exc)) from exc

    def _tags(self, values: list[str]) -> list[str]:
        try:
            return normalize_tags(values)
        except ValueError as exc:
            raise dynamic_error(ErrBadRequest, str(exc)) from exc

    def _rows(self, rows: list[ApiInterfaceRow], location: str) -> list[dict[str, Any]]:
        try:
            return normalize_rows(rows, location=location)  # type: ignore[arg-type]
        except ValueError as exc:
            raise dynamic_error(ErrBadRequest, str(exc)) from exc

    def _json_value(self, value: Any) -> Any | None:
        try:
            return parse_json_value(value)
        except ValueError as exc:
            raise dynamic_error(ErrBadRequest, str(exc)) from exc

    def _text(self, value: str, label: str, maximum: int) -> str:
        text = str(value or "").strip()
        if not text or len(text) > maximum:
            raise dynamic_error(ErrBadRequest, f"{label}不能为空且不能超过 {maximum} 个字符")
        return text


__all__ = [
    "ApiInterfaceService",
    "dump_interface",
    "dump_list_item",
]
