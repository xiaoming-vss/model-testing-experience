from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from testing_agent.handlers.generation_candidate_workflow import (
    adopt_candidate,
    get_current_stage,
    import_current_stage,
    initialize_candidate_chain,
    preview_candidate_adoption,
    preview_current_import,
    revise_candidate_stage,
    run_candidate_stage,
)
from testing_agent.handlers.generation_candidates import (
    check_ui_candidate_source,
    derive_generation_candidate,
    dispose_generation_candidate,
    edit_generation_candidate,
    get_current_candidate_relations,
    get_generation_candidate,
    list_generation_candidates,
    run_current_candidate_relations,
)
from testing_agent.handlers.generation_chain import (
    check_ui_generation_source,
    get_generation_chain_view,
    get_generation_chains,
    get_ui_generation_source_options,
)
from testing_agent.handlers.repository_profile_candidates import (
    adopt_profile_candidate,
    clear_current_profile,
    dispose_profile_candidate,
    get_current_profile,
    get_profile_candidate,
    list_profile_candidates,
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
from testing_agent.schemas.generation_candidates import (
    AdoptionCheck,
    CandidateAdoptResult,
    CandidateChainInitializeResult,
    CandidateDeriveResult,
    CandidateDetailView,
    CandidateDispositionResult,
    CandidateListView,
    CandidateRelationsRunResult,
    CandidateRelationsView,
    CandidateRunResult,
    CurrentClearResult,
    CurrentImportPreviewResult,
    CurrentImportResult,
    CurrentStageView,
)
from testing_agent.schemas.generation_chain import (
    GenerationChainOverview,
    GenerationChainView,
    UiGenerationSourceCheck,
    UiGenerationSourceOptions,
)
from testing_agent.schemas.requirement import (
    RequirementListItemResponse,
    RequirementMetadataResponse,
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
    response_model=ApiResponse[ListResponse[RequirementMetadataResponse]],
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
    "/requirements/{requirement_id}/repository-profile/candidates",
    response_model=ApiResponse[CandidateListView],
)(list_profile_candidates)
router.get(
    "/requirements/{requirement_id}/repository-profile/candidates/{candidate_id}",
    response_model=ApiResponse[CandidateDetailView],
)(get_profile_candidate)
router.post(
    "/requirements/{requirement_id}/repository-profile/candidates/{candidate_id}/disposition",
    response_model=ApiResponse[CandidateDispositionResult],
)(dispose_profile_candidate)
router.get(
    "/requirements/{requirement_id}/repository-profile/current",
    response_model=ApiResponse[CurrentStageView],
)(get_current_profile)
router.post(
    "/requirements/{requirement_id}/repository-profile/current/adopt",
    response_model=ApiResponse[CandidateAdoptResult],
)(adopt_profile_candidate)
router.post(
    "/requirements/{requirement_id}/repository-profile/current/clear",
    response_model=ApiResponse[CurrentClearResult],
)(clear_current_profile)

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
router.post(
    "/requirements/{requirement_id}/generation/{kind}/candidate-chain",
    response_model=ApiResponse[CandidateChainInitializeResult],
)(initialize_candidate_chain)
router.get(
    "/requirements/{requirement_id}/generation/{kind}/stages/{stage}/current",
    response_model=ApiResponse[CurrentStageView],
)(get_current_stage)
router.post(
    "/requirements/{requirement_id}/generation/{kind}/stages/{stage}/candidate-run",
    response_model=ApiResponse[CandidateRunResult],
)(run_candidate_stage)
router.post(
    "/requirements/{requirement_id}/generation/{kind}/stages/{stage}/adoption/check",
    response_model=ApiResponse[AdoptionCheck],
)(preview_candidate_adoption)
router.post(
    "/requirements/{requirement_id}/generation/{kind}/stages/{stage}/adoption",
    response_model=ApiResponse[CandidateAdoptResult],
)(adopt_candidate)
router.post(
    "/requirements/{requirement_id}/generation/{kind}/stages/{stage}/current/import-preview",
    response_model=ApiResponse[CurrentImportPreviewResult],
)(preview_current_import)
router.post(
    "/requirements/{requirement_id}/generation/{kind}/stages/{stage}/current/import",
    response_model=ApiResponse[CurrentImportResult],
)(import_current_stage)
router.get(
    "/requirements/{requirement_id}/generation/{kind}/stages/{stage}/candidates",
    response_model=ApiResponse[CandidateListView],
)(list_generation_candidates)
router.get(
    "/requirements/{requirement_id}/generation/{kind}/stages/{stage}/candidates/{candidate_id}",
    response_model=ApiResponse[CandidateDetailView],
)(get_generation_candidate)
router.post(
    "/requirements/{requirement_id}/generation/ui/stages/{stage}/candidates/{candidate_id}/source-check",
    response_model=ApiResponse[UiGenerationSourceCheck],
)(check_ui_candidate_source)
router.get(
    "/requirements/{requirement_id}/generation/function/relations/current",
    response_model=ApiResponse[CandidateRelationsView],
)(get_current_candidate_relations)
router.post(
    "/requirements/{requirement_id}/generation/function/relations/current/run",
    response_model=ApiResponse[CandidateRelationsRunResult],
)(run_current_candidate_relations)
router.post(
    "/requirements/{requirement_id}/generation/{kind}/stages/{stage}/candidates/{candidate_id}/disposition",
    response_model=ApiResponse[CandidateDispositionResult],
)(dispose_generation_candidate)
router.put(
    "/requirements/{requirement_id}/generation/{kind}/stages/{stage}/candidates/{candidate_id}",
    response_model=ApiResponse[CandidateDetailView],
)(edit_generation_candidate)
router.post(
    "/requirements/{requirement_id}/generation/{kind}/stages/{stage}/candidates/{candidate_id}/derive",
    response_model=ApiResponse[CandidateDeriveResult],
)(derive_generation_candidate)
router.post(
    "/requirements/{requirement_id}/generation/{kind}/stages/{stage}/candidates/{candidate_id}/revision",
    response_model=ApiResponse[CandidateRunResult],
)(revise_candidate_stage)
