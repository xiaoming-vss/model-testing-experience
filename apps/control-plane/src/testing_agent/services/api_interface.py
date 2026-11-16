from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError

from testing_agent.core.errors import (
    ErrApiInterfaceGroupNameAlreadyUse,
    ErrApiInterfaceGroupNotFound,
    ErrApiInterfaceIdentityAlreadyUse,
    ErrApiInterfaceNotFound,
    ErrApiInterfacePathParamsMismatch,
    ErrApiInterfaceRequirementMismatch,
    ErrBadRequest,
    ErrSoftwareRepositoryNotFound,
    dynamic_error,
)
from testing_agent.core.sid import new_id
from testing_agent.domain.api_interface import (
    UNTAGGED_GROUP_NAME,
    group_name,
    normalize_method,
    normalize_path,
    normalize_rows,
    normalize_tags,
    parse_json_value,
    path_key,
    replace_group_tag,
    set_group_tag,
    validate_path_parameters,
)
from testing_agent.domain.api_interface_query import ApiInterfaceQuery
from testing_agent.models.api_interface import ApiInterface
from testing_agent.models.requirement import Requirement
from testing_agent.models.software_repository import SoftwareRepository
from testing_agent.models.sprint import Sprint
from testing_agent.repositories.api_interface import ApiInterfaceRepository
from testing_agent.repositories.software_repository import SoftwareRepositoryRepository
from testing_agent.schemas.api_interface import (
    ApiInterfaceCreateRequest,
    ApiInterfaceGroupCreateRequest,
    ApiInterfaceGroupDeleteRequest,
    ApiInterfaceGroupMutationResponse,
    ApiInterfaceGroupRenameRequest,
    ApiInterfaceListItem,
    ApiInterfaceMoveGroupRequest,
    ApiInterfaceResponse,
    ApiInterfaceRow,
    ApiInterfaceUpdateRequest,
)
from testing_agent.services.project_access import ProjectAction, require_project_id
from testing_agent.services.resource_deletion import ResourceDeletion, SqlResourceDeletion


def _requirement_rows(interface: ApiInterface) -> list[dict[str, str]]:
    return list(getattr(interface, "requirements", []) or [])


def dump_interface(
    interface: ApiInterface, *, software_repository_name: str = ""
) -> dict[str, Any]:
    data = {
        "interface_id": interface.interface_id,
        "software_repository_id": interface.software_repository_id,
        "software_repository_name": software_repository_name
        or getattr(interface, "software_repository_name", ""),
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
        "security": interface.security_json,
        "security_schemes": interface.security_schemes_json,
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
        "software_repository_id": interface.software_repository_id,
        "software_repository_name": getattr(interface, "software_repository_name", ""),
        "name": interface.name,
        "method": interface.method,
        "path": interface.path,
        "description": interface.description,
        "tags": interface.tags_json or [],
        "requirements": _requirement_rows(interface),
        "source_type": interface.source_type,
        "updated_at": interface.updated_at,
    }
    return ApiInterfaceListItem.model_validate(data).model_dump(by_alias=True, mode="json")


class ApiInterfaceService:
    def __init__(
        self,
        repository: ApiInterfaceRepository,
        software_repositories: SoftwareRepositoryRepository,
        *,
        deletion: ResourceDeletion | None = None,
    ) -> None:
        self.repository = repository
        self.software_repositories = software_repositories
        self.deletion = deletion or SqlResourceDeletion()

    async def list_project(self, user_id: str, query: ApiInterfaceQuery) -> dict[str, Any]:
        await require_project_id(self.repository.session, user_id, query.project_id, action="read")
        interfaces, total = await self.repository.list_by_project(query)
        return {
            "items": [dump_list_item(interface) for interface in interfaces],
            "total": total,
        }

    async def list_software_repository(
        self, user_id: str, software_repository_id: str, query: ApiInterfaceQuery
    ) -> dict[str, Any]:
        software_repository = await self._accessible_software_repository(
            user_id, software_repository_id, action="read"
        )
        interfaces, total = await self.repository.list_by_software_repository(
            software_repository.software_repository_id, query
        )
        return {
            "items": [dump_list_item(interface) for interface in interfaces],
            "total": total,
        }

    async def get(self, user_id: str, interface_id: str) -> dict[str, Any]:
        interface, software_repository = await self._accessible_interface(
            user_id, interface_id, action="read"
        )
        await self.repository.attach_requirements([interface])
        return dump_interface(interface, software_repository_name=software_repository.name)

    async def create_group(
        self,
        user_id: str,
        software_repository_id: str,
        body: ApiInterfaceGroupCreateRequest,
    ) -> dict[str, Any]:
        repository = await self._accessible_software_repository(
            user_id, software_repository_id, action="write", for_update=True
        )
        target = self._group_name(body.group_name)
        interfaces = await self.repository.list_all_by_software_repository_for_update(
            software_repository_id
        )
        groups = {group_name(interface.tags_json) for interface in interfaces}
        groups.update(self._persisted_groups(repository))
        if target in groups:
            raise ErrApiInterfaceGroupNameAlreadyUse()
        repository.interface_groups_json = [*self._persisted_groups(repository), target]
        await self.repository.commit()
        return self._group_mutation(target, target, 0)

    async def rename_group(
        self,
        user_id: str,
        software_repository_id: str,
        body: ApiInterfaceGroupRenameRequest,
    ) -> dict[str, Any]:
        repository = await self._accessible_software_repository(
            user_id, software_repository_id, action="write", for_update=True
        )
        current = self._group_name(body.current_group_name)
        target = self._group_name(body.new_group_name)
        interfaces = await self.repository.list_all_by_software_repository_for_update(
            software_repository_id
        )
        persisted = self._persisted_groups(repository)
        groups = {group_name(interface.tags_json) for interface in interfaces}
        groups.update(persisted)
        if current not in groups:
            raise ErrApiInterfaceGroupNotFound()
        if current == target:
            return self._group_mutation(current, target, 0)
        if target in groups:
            raise ErrApiInterfaceGroupNameAlreadyUse()
        changed = False
        if current in persisted:
            repository.interface_groups_json = [
                target if name == current else name for name in persisted
            ]
            changed = True
        updated = 0
        for interface in interfaces:
            if group_name(interface.tags_json) != current:
                continue
            new_tags = replace_group_tag(interface.tags_json, target)
            if new_tags != (interface.tags_json or []):
                interface.tags_json = new_tags
                interface.version += 1
                updated += 1
        if updated or changed:
            await self.repository.commit()
        return self._group_mutation(current, target, updated)

    async def delete_group(
        self,
        user_id: str,
        software_repository_id: str,
        body: ApiInterfaceGroupDeleteRequest,
    ) -> dict[str, Any]:
        repository = await self._accessible_software_repository(
            user_id, software_repository_id, action="write", for_update=True
        )
        current = self._group_name(body.group_name)
        interfaces = await self.repository.list_all_by_software_repository_for_update(
            software_repository_id
        )
        persisted = self._persisted_groups(repository)
        groups = {group_name(interface.tags_json) for interface in interfaces}
        groups.update(persisted)
        if current not in groups:
            raise ErrApiInterfaceGroupNotFound()
        changed = False
        if current in persisted:
            repository.interface_groups_json = [name for name in persisted if name != current]
            changed = True
        updated = 0
        for interface in interfaces:
            if group_name(interface.tags_json) != current:
                continue
            # Removing a group puts its interfaces into 未分类; secondary tags are cleared too.
            interface.tags_json = []
            interface.version += 1
            updated += 1
        if updated or changed:
            await self.repository.commit()
        return self._group_mutation(current, "", updated)

    async def move_to_group(
        self, user_id: str, interface_id: str, body: ApiInterfaceMoveGroupRequest
    ) -> dict[str, Any]:
        interface, software_repository = await self._accessible_interface(
            user_id, interface_id, action="write", for_update=True
        )
        target = "" if body.group_name is None else str(body.group_name).strip()
        if target:
            target = self._group_name(target)
            new_tags = set_group_tag(interface.tags_json, target)
        else:
            new_tags = []
        if new_tags != (interface.tags_json or []):
            interface.tags_json = new_tags
            interface.version += 1
            await self.repository.commit()
            await self.repository.refresh(interface)
        await self.repository.attach_requirements([interface])
        return dump_interface(interface, software_repository_name=software_repository.name)

    @staticmethod
    def _persisted_groups(repository: SoftwareRepository) -> list[str]:
        names: list[str] = []
        for raw in repository.interface_groups_json or []:
            name = str(raw or "").strip()
            if not name or name == UNTAGGED_GROUP_NAME or name in names:
                continue
            names.append(name)
        return names

    @staticmethod
    def _group_mutation(current: str, target: str, updated: int) -> dict[str, Any]:
        return ApiInterfaceGroupMutationResponse(
            group_name=current,
            new_group_name=target,
            updated_count=updated,
        ).model_dump(by_alias=True, mode="json")

    async def create(
        self, user_id: str, software_repository_id: str, body: ApiInterfaceCreateRequest
    ) -> dict[str, Any]:
        # Lock the software repository so a concurrent deletion cannot pass its
        # interface count check between the ownership check and the insert below.
        software_repository = await self._accessible_software_repository(
            user_id, software_repository_id, action="write", for_update=True
        )
        payload = self._create_payload(body)
        if (
            await self.repository.get_by_identity(
                software_repository_id, payload["method"], payload["path_key"]
            )
            is not None
        ):
            raise ErrApiInterfaceIdentityAlreadyUse()
        requirements = await self._requirements(
            software_repository.project_id, body.requirement_ids
        )
        interface = ApiInterface(
            interface_id=new_id(),
            software_repository_id=software_repository_id,
            version=1,
            source_type="manual",
            source_name="",
            source_url="",
            source_version="",
            source_imported_at=None,
            security_json=None,
            security_schemes_json=None,
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
        return dump_interface(interface, software_repository_name=software_repository.name)

    async def update(
        self, user_id: str, interface_id: str, body: ApiInterfaceUpdateRequest
    ) -> dict[str, Any]:
        interface, software_repository = await self._accessible_interface(
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
            exists = await self.repository.get_by_identity(
                interface.software_repository_id, method, new_path_key
            )
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
        if "requirement_ids" in fields:
            if body.requirement_ids is None:
                raise ErrBadRequest()
            requirements = await self._requirements(
                software_repository.project_id, body.requirement_ids
            )
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
        return dump_interface(interface, software_repository_name=software_repository.name)

    async def delete(self, user_id: str, interface_id: str) -> dict[str, Any]:
        interface, _software_repository = await self._accessible_interface(
            user_id, interface_id, action="write", for_update=True
        )
        await self.repository.delete_requirements(interface_id)
        await self.deletion.delete(self.repository.session, interface)
        await self.repository.commit()
        return {}

    async def _accessible_software_repository(
        self,
        user_id: str,
        software_repository_id: str,
        *,
        action: ProjectAction,
        for_update: bool = False,
    ) -> SoftwareRepository:
        software_repository = (
            await self.software_repositories.get_for_update(software_repository_id)
            if for_update
            else await self.software_repositories.get(software_repository_id)
        )
        if software_repository is None:
            raise ErrSoftwareRepositoryNotFound()
        await require_project_id(
            self.repository.session, user_id, software_repository.project_id, action=action
        )
        return software_repository

    async def _accessible_interface(
        self,
        user_id: str,
        interface_id: str,
        *,
        action: ProjectAction,
        for_update: bool = False,
    ) -> tuple[ApiInterface, SoftwareRepository]:
        interface = (
            await self.repository.get_for_update(interface_id)
            if for_update
            else await self.repository.get(interface_id)
        )
        if interface is None:
            raise ErrApiInterfaceNotFound()
        software_repository = await self.software_repositories.get(interface.software_repository_id)
        if software_repository is None:
            raise ErrApiInterfaceNotFound()
        await require_project_id(
            self.repository.session, user_id, software_repository.project_id, action=action
        )
        return interface, software_repository

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

    def _group_name(self, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise dynamic_error(ErrBadRequest, "分组名称不能为空")
        if text == UNTAGGED_GROUP_NAME:
            raise dynamic_error(ErrBadRequest, "分组名称不能为「未分类」")
        try:
            return normalize_tags([text])[0]
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
