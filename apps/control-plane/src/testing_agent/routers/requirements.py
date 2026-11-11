from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from testing_agent.handlers.generation_chain import (
    check_ui_generation_source,
    delete_generation_chain_version,
    get_generation_chain_import_options,
    get_generation_chain_version,
    get_generation_chain_view,
    get_generation_chains,
    get_ui_generation_source_options,
    import_generation_chain_version,
    review_generation_chain_stage,
    revise_generation_chain_stage,
    run_generation_chain_stage,
    save_generation_chain_stage_draft,
)
from testing_agent.handlers.requirement import (
    create_requirement,
    delete_requirement,
    download_requirement_document,
    get_requirement,
    list_project_requirement_options,
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
from testing_agent.schemas.generation_chain import (
    GenerationChainDeleteVersionResponse,
    GenerationChainImportOptions,
    GenerationChainImportResponse,
    GenerationChainOverview,
    GenerationChainVersionDetail,
    GenerationChainView,
    UiGenerationSourceCheck,
    UiGenerationSourceOptions,
)
from testing_agent.schemas.requirement import (
    RequirementListItemResponse,
    RequirementOptionResponse,
    RequirementResponse,
)
from testing_agent.schemas.requirement_design import RequirementDesignResponse

router = APIRouter()

router.get(
    "/projects/{project_id}/requirements/options",
    response_model=ApiResponse[ListResponse[RequirementOptionResponse]],
)(list_project_requirement_options)
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

router.get(
    "/requirements/{requirement_id}/generation",
    response_model=ApiResponse[GenerationChainOverview],
)(get_generation_chains)
router.get(
    "/requirements/{requirement_id}/generation/ui/source-options",
    response_model=ApiResponse[UiGenerationSourceOptions],
)(get_ui_generation_source_options)
router.post(
    "/requirements/{requirement_id}/generation/ui/source-check",
    response_model=ApiResponse[UiGenerationSourceCheck],
)(check_ui_generation_source)
router.get(
    "/requirements/{requirement_id}/generation/{kind}",
    response_model=ApiResponse[GenerationChainView],
)(get_generation_chain_view)
router.get(
    "/requirements/{requirement_id}/generation/{kind}/versions/{version_id}",
    response_model=ApiResponse[GenerationChainVersionDetail],
)(get_generation_chain_version)
router.get(
    "/requirements/{requirement_id}/generation/{kind}/versions/{version_id}/import-options",
    response_model=ApiResponse[GenerationChainImportOptions],
)(get_generation_chain_import_options)
router.post(
    "/requirements/{requirement_id}/generation/{kind}/versions/{version_id}/import",
    response_model=ApiResponse[GenerationChainImportResponse],
)(import_generation_chain_version)
router.post(
    "/requirements/{requirement_id}/generation/{kind}/stages/{stage}/run",
    response_model=ApiResponse[GenerationChainView],
)(run_generation_chain_stage)
router.post(
    "/requirements/{requirement_id}/generation/{kind}/stages/{stage}/revision",
    response_model=ApiResponse[GenerationChainView],
)(revise_generation_chain_stage)
router.post(
    "/requirements/{requirement_id}/generation/{kind}/stages/{stage}/review",
    response_model=ApiResponse[GenerationChainView],
)(review_generation_chain_stage)
router.put(
    "/requirements/{requirement_id}/generation/{kind}/stages/{stage}/draft",
    response_model=ApiResponse[GenerationChainView],
)(save_generation_chain_stage_draft)
router.delete(
    "/requirements/{requirement_id}/generation/{kind}/versions/{version_id}",
    response_model=ApiResponse[GenerationChainDeleteVersionResponse],
)(delete_generation_chain_version)
