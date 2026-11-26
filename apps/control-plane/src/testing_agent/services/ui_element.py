from __future__ import annotations

import hashlib
import json

from pydantic import ValidationError

from testing_agent.core.errors import (
    ErrBadRequest,
    ErrNotFound,
    ErrSoftwareRepositoryNotFound,
    ErrUiElementDuplicate,
    ErrUiElementGroupDuplicate,
    ErrUiElementGroupNotEmpty,
    ErrUiElementVersionConflict,
    dynamic_error,
    validation_error_detail,
)
from testing_agent.core.sid import new_id
from testing_agent.models.ui_element import UiElement, UiElementGroup
from testing_agent.repositories.software_repository import SoftwareRepositoryRepository
from testing_agent.repositories.ui_element import UiElementRepository
from testing_agent.schemas.common import ListResponse
from testing_agent.schemas.ui_element import (
    GroupKind,
    UiElementCreate,
    UiElementDetail,
    UiElementGroupCreate,
    UiElementGroupView,
    UiElementListFilters,
    UiElementSummary,
    UiElementUpdate,
)
from testing_agent.services.project_access import require_project_id
from testing_agent.services.resource_deletion import SqlResourceDeletion

COMMON_GROUP_NAME = "公共元素"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _locator_key(body: UiElementCreate) -> str:
    return _digest(
        json.dumps([body.scope, body.locator_type, body.locator_value], ensure_ascii=False)
    )


def _group_view(group: UiElementGroup, count: int) -> UiElementGroupView:
    return UiElementGroupView.model_validate(
        {
            "group_id": group.group_id,
            "kind": group.kind,
            "name": group.name,
            "route_template": group.route_template,
            "element_count": count,
        }
    )


class UiElementService:
    def __init__(
        self, repository: UiElementRepository, software_repositories: SoftwareRepositoryRepository
    ) -> None:
        self.repository = repository
        self.software_repositories = software_repositories

    async def list_groups(self, actor: str, repository_id: str) -> ListResponse[UiElementGroupView]:
        await self._authorize(actor, repository_id)
        groups = await self.repository.groups(repository_id)
        return ListResponse(
            items=[_group_view(group, count) for group, count in groups], total=len(groups)
        )

    async def create_group(
        self, actor: str, repository_id: str, body: UiElementGroupCreate
    ) -> UiElementGroupView:
        await self._authorize(actor, repository_id, write=True)
        key = _digest(body.route_template)
        if await self.repository.find_group(repository_id, "page", key) is not None:
            raise ErrUiElementGroupDuplicate()
        group = self._new_group(actor, repository_id, "page", body.name, body.route_template)
        result = _group_view(group, 0)
        await self.repository.commit()
        return result

    async def delete_group(self, actor: str, group_id: str) -> None:
        group = await self.repository.group(group_id)
        if group is None:
            raise ErrNotFound()
        await self._authorize(actor, group.software_repository_id, write=True)
        group = await self.repository.group(group_id, for_update=True)
        if group is None:
            raise ErrNotFound()
        if await self.repository.group_has_elements(group_id):
            raise ErrUiElementGroupNotEmpty()
        await SqlResourceDeletion().delete(self.repository.session, group)
        await self.repository.commit()

    async def list_elements(
        self, actor: str, repository_id: str, filters: UiElementListFilters
    ) -> ListResponse[UiElementSummary]:
        await self._authorize(actor, repository_id)
        if filters.group_id:
            await self._get_group(repository_id, filters.group_id)
        items, total = await self.repository.list_elements(repository_id, filters)
        return ListResponse(
            items=[UiElementSummary.model_validate(item) for item in items], total=total
        )

    async def detail(self, actor: str, element_id: str) -> UiElementDetail:
        _, element = await self._access_element(actor, element_id)
        return UiElementDetail.model_validate(element)

    async def create_element(
        self, actor: str, repository_id: str, body: UiElementCreate
    ) -> UiElementDetail:
        await self._authorize(actor, repository_id, write=True)
        group = await self._resolve_group(actor, repository_id, body.group_id)
        key = _locator_key(body)
        await self._check_location(group.group_id, key)
        element = UiElement(
            element_id=new_id(),
            group_id=group.group_id,
            locator_key=key,
            parameters_json=[param.model_dump() for param in body.parameters],
            created_by_user_id=actor,
            **body.model_dump(exclude={"group_id", "parameters"}),
        )
        self.repository.add(element)
        await self.repository.flush()
        result = UiElementDetail.model_validate(element)
        await self.repository.commit()
        return result

    async def update_element(
        self, actor: str, element_id: str, body: UiElementUpdate
    ) -> UiElementDetail:
        repository_id, element = await self._access_element(actor, element_id, write=True)
        if element.version != body.version:
            raise ErrUiElementVersionConflict()
        stored = {
            "group_id": element.group_id,
            "name": element.name,
            "scope": element.scope,
            "locator_type": element.locator_type,
            "locator_value": element.locator_value,
            "parameters": element.parameters_json,
        }
        requested = body.model_dump(exclude_unset=True, exclude={"version"})
        try:
            values = UiElementCreate.model_validate(stored | requested)
        except ValidationError as exc:
            raise dynamic_error(ErrBadRequest, validation_error_detail(list(exc.errors()))) from exc
        group = await self._resolve_group(actor, repository_id, values.group_id)
        new_values = values.model_dump() | {"group_id": group.group_id}
        if new_values == stored:
            return UiElementDetail.model_validate(element)

        key = _locator_key(values)
        if group.group_id != element.group_id or key != element.locator_key:
            await self._check_location(group.group_id, key, element_id=element_id)
            element.verification_status = "pending"
        element.group_id = group.group_id
        element.name = values.name
        element.scope = values.scope
        element.locator_type = values.locator_type
        element.locator_value = values.locator_value
        element.locator_key = key
        element.parameters_json = [param.model_dump() for param in values.parameters]
        element.version += 1
        await self.repository.flush()
        result = UiElementDetail.model_validate(element)
        await self.repository.commit()
        return result

    async def delete_element(self, actor: str, element_id: str, version: int) -> None:
        _, element = await self._access_element(actor, element_id, write=True)
        if element.version != version:
            raise ErrUiElementVersionConflict()
        await SqlResourceDeletion().delete(self.repository.session, element)
        await self.repository.commit()

    async def _authorize(self, actor: str, repository_id: str, *, write: bool = False) -> None:
        # All element-library writes lock the repository first, including repository
        # deletion and rebinding, before checking the group and element identities.
        repository = (
            await self.software_repositories.get_for_update(repository_id)
            if write
            else await self.software_repositories.get(repository_id)
        )
        if repository is None:
            raise ErrSoftwareRepositoryNotFound()
        await require_project_id(
            self.repository.session,
            actor,
            repository.project_id,
            action="write" if write else "read",
        )

    async def _access_element(
        self, actor: str, element_id: str, *, write: bool = False
    ) -> tuple[str, UiElement]:
        repository_id = await self.repository.element_repository_id(element_id)
        if repository_id is None:
            raise ErrNotFound()
        await self._authorize(actor, repository_id, write=write)
        element = await self.repository.element(element_id, for_update=write)
        if element is None:
            raise ErrNotFound()
        return repository_id, element

    async def _get_group(
        self, repository_id: str, group_id: str, *, write: bool = False
    ) -> UiElementGroup:
        group = await self.repository.group(group_id, repository_id=repository_id, for_update=write)
        if group is None:
            raise ErrNotFound()
        return group

    async def _resolve_group(
        self, actor: str, repository_id: str, group_id: str | None
    ) -> UiElementGroup:
        if group_id is not None:
            return await self._get_group(repository_id, group_id, write=True)
        group = await self.repository.find_group(repository_id, "common", _digest(""))
        if group is None:
            group = self._new_group(actor, repository_id, "common", COMMON_GROUP_NAME, "")
            await self.repository.flush()
        return group

    def _new_group(
        self, actor: str, repository_id: str, kind: GroupKind, name: str, route: str
    ) -> UiElementGroup:
        group = UiElementGroup(
            group_id=new_id(),
            software_repository_id=repository_id,
            kind=kind,
            name=name,
            route_template=route,
            route_key=_digest(route),
            created_by_user_id=actor,
        )
        self.repository.add(group)
        return group

    async def _check_location(
        self, group_id: str, key: str, *, element_id: str | None = None
    ) -> None:
        existing = await self.repository.element_with_locator(group_id, key)
        if existing is not None and existing.element_id != element_id:
            raise dynamic_error(
                ErrUiElementDuplicate,
                ErrUiElementDuplicate.message,
                {"elementId": existing.element_id},
            )
