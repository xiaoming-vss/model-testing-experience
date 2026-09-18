from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import get_current_user_id, get_resource_binding_service
from testing_agent.core.errors import success_payload
from testing_agent.schemas.resource_binding import (
    ResourceBindingRequest,
    UpdateRequirementBindingRequest,
    UpdateResourceBindingRequest,
)
from testing_agent.services.resource_binding import ResourceBindingService


async def bind_project(
    project_id: str,
    body: ResourceBindingRequest,
    user_id: str = Depends(get_current_user_id),
    service: ResourceBindingService = Depends(get_resource_binding_service),
):
    return success_payload(
        await service.create("project", project_id, body.model_dump(by_alias=True), user_id)
    )


async def list_project_bindings(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ResourceBindingService = Depends(get_resource_binding_service),
):
    return success_payload(await service.list("project", project_id, user_id))


async def update_project_binding(
    project_id: str,
    binding_id: str,
    body: UpdateResourceBindingRequest,
    user_id: str = Depends(get_current_user_id),
    service: ResourceBindingService = Depends(get_resource_binding_service),
):
    return success_payload(
        await service.update(
            "project", project_id, binding_id, body.model_dump(by_alias=True), user_id
        )
    )


async def unbind_project(
    project_id: str,
    binding_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ResourceBindingService = Depends(get_resource_binding_service),
):
    return success_payload(await service.delete("project", project_id, binding_id, user_id))


async def bind_sprint(
    sprint_id: str,
    body: ResourceBindingRequest,
    user_id: str = Depends(get_current_user_id),
    service: ResourceBindingService = Depends(get_resource_binding_service),
):
    return success_payload(
        await service.create("sprint", sprint_id, body.model_dump(by_alias=True), user_id)
    )


async def list_sprint_bindings(
    sprint_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ResourceBindingService = Depends(get_resource_binding_service),
):
    return success_payload(await service.list("sprint", sprint_id, user_id))


async def unbind_sprint(
    sprint_id: str,
    binding_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ResourceBindingService = Depends(get_resource_binding_service),
):
    return success_payload(await service.delete("sprint", sprint_id, binding_id, user_id))


async def bind_requirement(
    requirement_id: str,
    body: ResourceBindingRequest,
    user_id: str = Depends(get_current_user_id),
    service: ResourceBindingService = Depends(get_resource_binding_service),
):
    return success_payload(
        await service.create("requirement", requirement_id, body.model_dump(by_alias=True), user_id)
    )


async def list_requirement_bindings(
    requirement_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ResourceBindingService = Depends(get_resource_binding_service),
):
    return success_payload(await service.list("requirement", requirement_id, user_id))


async def update_requirement_binding(
    requirement_id: str,
    binding_id: str,
    body: UpdateRequirementBindingRequest,
    user_id: str = Depends(get_current_user_id),
    service: ResourceBindingService = Depends(get_resource_binding_service),
):
    return success_payload(
        await service.update(
            "requirement",
            requirement_id,
            binding_id,
            # 未传字段不出现在 payload 中,避免把显式省略误判为清空。
            body.model_dump(by_alias=True, exclude_none=True),
            user_id,
        )
    )


async def unbind_requirement(
    requirement_id: str,
    binding_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ResourceBindingService = Depends(get_resource_binding_service),
):
    return success_payload(await service.delete("requirement", requirement_id, binding_id, user_id))


async def update_sprint_binding(
    sprint_id: str,
    binding_id: str,
    body: UpdateResourceBindingRequest,
    user_id: str = Depends(get_current_user_id),
    service: ResourceBindingService = Depends(get_resource_binding_service),
):
    return success_payload(
        await service.update(
            "sprint", sprint_id, binding_id, body.model_dump(by_alias=True), user_id
        )
    )
