from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from testing_agent.handlers.requirement import (
    create_requirement,
    delete_requirement,
    download_requirement_document,
    get_requirement,
    list_project_requirements,
    list_requirements,
    update_requirement,
)

# Requirement-scoped UI keeps legacy task/detail URLs intact.
from testing_agent.handlers.requirement_design import (
    configure_requirement_design,
    get_requirement_design,
    list_requirement_design_runs,
    start_requirement_design,
)
from testing_agent.schemas.ai_generate_task import (
    AiGenerateRunHistoryResponse,
    AiGenerateTaskResponse,
    AiGenerateTaskRunResponse,
)
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse
from testing_agent.schemas.requirement import RequirementListItemResponse, RequirementResponse
from testing_agent.schemas.requirement_design import RequirementDesignResponse

router = APIRouter()

router.get(
    "/projects/{project_id}/requirements",
    response_model=ApiResponse[ListResponse[RequirementListItemResponse]],
)(list_project_requirements)

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


router.get(
    "/requirements/{requirement_id}/design",
    response_model=ApiResponse[RequirementDesignResponse],
)(get_requirement_design)
router.get(
    "/requirements/{requirement_id}/design/{kind}/runs",
    response_model=ApiResponse[AiGenerateRunHistoryResponse],
)(list_requirement_design_runs)
router.post(
    "/requirements/{requirement_id}/design/{kind}/configuration",
    response_model=ApiResponse[AiGenerateTaskResponse],
)(configure_requirement_design)
router.post(
    "/requirements/{requirement_id}/design/{kind}/run",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(start_requirement_design)
