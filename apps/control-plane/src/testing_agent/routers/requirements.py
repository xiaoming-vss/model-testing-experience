from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from testing_agent.handlers.requirement import (
    create_requirement,
    delete_requirement,
    download_requirement_document,
    get_requirement,
    list_requirements,
    update_requirement,
)
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse
from testing_agent.schemas.requirement import RequirementResponse

router = APIRouter()

router.post(
    "/sprints/{sprint_id}/requirements",
    response_model=ApiResponse[RequirementResponse],
)(create_requirement)
router.get(
    "/sprints/{sprint_id}/requirements",
    response_model=ApiResponse[ListResponse[RequirementResponse]],
)(list_requirements)
router.get(
    "/requirements/{requirement_id}",
    response_model=ApiResponse[RequirementResponse],
)(get_requirement)
router.patch(
    "/requirements/{requirement_id}",
    response_model=ApiResponse[RequirementResponse],
)(update_requirement)
router.get(
    "/requirements/{requirement_id}/download",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)(download_requirement_document)
router.delete("/requirements/{requirement_id}", response_model=ApiResponse[EmptyData])(
    delete_requirement
)
