from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.resource_binding import (
    bind_project,
    bind_requirement,
    bind_sprint,
    list_project_bindings,
    list_requirement_bindings,
    list_sprint_bindings,
    unbind_project,
    unbind_requirement,
    unbind_sprint,
    update_project_binding,
    update_requirement_binding,
    update_sprint_binding,
)
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse
from testing_agent.schemas.resource_binding import ResourceBindingResponse

router = APIRouter()

router.post(
    "/projects/{project_id}/bindings",
    response_model=ApiResponse[ResourceBindingResponse],
)(bind_project)
router.get(
    "/projects/{project_id}/bindings",
    response_model=ApiResponse[ListResponse[ResourceBindingResponse]],
)(list_project_bindings)
router.patch(
    "/projects/{project_id}/bindings/{binding_id}",
    response_model=ApiResponse[ResourceBindingResponse],
)(update_project_binding)
router.delete(
    "/projects/{project_id}/bindings/{binding_id}",
    response_model=ApiResponse[EmptyData],
)(unbind_project)
router.post(
    "/sprints/{sprint_id}/bindings",
    response_model=ApiResponse[ResourceBindingResponse],
)(bind_sprint)
router.get(
    "/sprints/{sprint_id}/bindings",
    response_model=ApiResponse[ListResponse[ResourceBindingResponse]],
)(list_sprint_bindings)
router.delete(
    "/sprints/{sprint_id}/bindings/{binding_id}",
    response_model=ApiResponse[EmptyData],
)(unbind_sprint)
router.post(
    "/requirements/{requirement_id}/bindings",
    response_model=ApiResponse[ResourceBindingResponse],
)(bind_requirement)
router.get(
    "/requirements/{requirement_id}/bindings",
    response_model=ApiResponse[ListResponse[ResourceBindingResponse]],
)(list_requirement_bindings)
router.patch(
    "/requirements/{requirement_id}/bindings/{binding_id}",
    response_model=ApiResponse[ResourceBindingResponse],
)(update_requirement_binding)
router.delete(
    "/requirements/{requirement_id}/bindings/{binding_id}",
    response_model=ApiResponse[EmptyData],
)(unbind_requirement)

router.patch(
    "/sprints/{sprint_id}/bindings/{binding_id}",
    response_model=ApiResponse[ResourceBindingResponse],
)(update_sprint_binding)
