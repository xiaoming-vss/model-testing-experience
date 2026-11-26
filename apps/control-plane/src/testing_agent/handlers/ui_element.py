from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query

from testing_agent.api.deps_auth import get_current_user_id
from testing_agent.api.deps_projects import get_ui_element_service
from testing_agent.core.errors import success_payload
from testing_agent.schemas.ui_element import (
    UiElementCreate,
    UiElementGroupCreate,
    UiElementListFilters,
    UiElementUpdate,
    VerificationStatus,
)
from testing_agent.services.ui_element import UiElementService

Actor = Annotated[str, Depends(get_current_user_id)]
Service = Annotated[UiElementService, Depends(get_ui_element_service)]


async def list_ui_element_groups(
    software_repository_id: str, actor: Actor, service: Service
) -> dict:
    return success_payload(await service.list_groups(actor, software_repository_id))


async def create_ui_element_group(
    software_repository_id: str, body: UiElementGroupCreate, actor: Actor, service: Service
) -> dict:
    return success_payload(await service.create_group(actor, software_repository_id, body))


async def delete_ui_element_group(group_id: str, actor: Actor, service: Service) -> dict:
    await service.delete_group(actor, group_id)
    return success_payload()


async def list_ui_elements(
    software_repository_id: str,
    actor: Actor,
    service: Service,
    group_id: Annotated[str | None, Query(alias="groupId", min_length=1, max_length=64)] = None,
    keyword: Annotated[str, Query(max_length=120)] = "",
    verification_status: Annotated[
        VerificationStatus | None, Query(alias="verificationStatus")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
) -> dict:
    filters = UiElementListFilters(
        group_id=group_id,
        keyword=keyword,
        verification_status=verification_status,
        page=page,
        page_size=page_size,
    )
    return success_payload(await service.list_elements(actor, software_repository_id, filters))


async def create_ui_element(
    software_repository_id: str, body: UiElementCreate, actor: Actor, service: Service
) -> dict:
    return success_payload(await service.create_element(actor, software_repository_id, body))


async def get_ui_element(element_id: str, actor: Actor, service: Service) -> dict:
    return success_payload(await service.detail(actor, element_id))


async def update_ui_element(
    element_id: str, body: UiElementUpdate, actor: Actor, service: Service
) -> dict:
    return success_payload(await service.update_element(actor, element_id, body))


async def delete_ui_element(
    element_id: str, version: Annotated[int, Query(ge=1)], actor: Actor, service: Service
) -> dict:
    await service.delete_element(actor, element_id, version)
    return success_payload()
