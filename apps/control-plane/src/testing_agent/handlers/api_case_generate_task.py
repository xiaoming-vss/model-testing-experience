from __future__ import annotations

from fastapi import Depends, Query

from testing_agent.api.deps import (
    get_current_user_id,
    get_generation_api_importer,
    get_generation_launcher,
    get_generation_queries,
    get_generation_review,
    get_generation_stages,
    get_generation_task_commands,
)
from testing_agent.core.errors import success_payload
from testing_agent.handlers.generation_guards import ensure_legacy_mutation_allowed
from testing_agent.schemas.ai_generate_task import (
    AiGenerateTaskImportRequest,
    AiGenerateTaskRequest,
    AiGenerateTaskResultRequest,
    AiGenerateTaskReviewRequest,
    AiGenerateTaskRunRequest,
)
from testing_agent.services.ai_candidate_review import GenerationCandidateReview
from testing_agent.services.ai_run_launcher import GenerationRunLauncher
from testing_agent.services.ai_stage_workflow import GenerationStageWorkflow
from testing_agent.services.ai_task_commands import GenerationTaskCommands
from testing_agent.services.ai_task_queries import GenerationQueries
from testing_agent.services.api_generate_import import ApiCandidateImporter


async def create_api_case_generate_task(
    project_id: str,
    body: AiGenerateTaskRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationTaskCommands = Depends(get_generation_task_commands),
):
    return success_payload(
        await service.create(
            "api",
            project_id,
            body.model_dump(by_alias=True, exclude_none=True),
            user_id,
        )
    )


async def list_api_case_generate_tasks(
    project_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    sprint_id: str = Query(default="", alias="sprintId"),
    requirement_id: str = Query(default="", alias="requirementId"),
    keyword: str = Query(default=""),
    status: str = Query(default=""),
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(
        await service.list(
            "api",
            project_id,
            user_id,
            page=page,
            page_size=page_size,
            sprint_id=sprint_id,
            requirement_id=requirement_id,
            keyword=keyword,
            status=status,
        )
    )


async def get_api_case_generate_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(await service.get("api", task_id, user_id))


async def update_api_case_generate_task(
    task_id: str,
    body: AiGenerateTaskRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationTaskCommands = Depends(get_generation_task_commands),
):
    return success_payload(
        await service.update(
            "api",
            task_id,
            body.model_dump(by_alias=True, exclude_none=True),
            user_id,
        )
    )


async def delete_api_case_generate_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationTaskCommands = Depends(get_generation_task_commands),
):
    return success_payload(await service.delete("api", task_id, user_id))


async def run_api_case_generate_task(
    task_id: str,
    body: AiGenerateTaskRunRequest | None = None,
    user_id: str = Depends(get_current_user_id),
    service: GenerationRunLauncher = Depends(get_generation_launcher),
):
    payload = body.model_dump(by_alias=True, exclude_none=True) if body else {}
    return success_payload(await service.launch("api", task_id, payload, user_id))


async def list_api_case_generate_task_runs(
    task_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(
        await service.list_run_summaries("api", task_id, user_id, page, page_size)
    )


async def get_api_case_generate_task_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(await service.get_run("api", run_id, user_id))


async def delete_api_case_generate_task_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationTaskCommands = Depends(get_generation_task_commands),
):
    await ensure_legacy_mutation_allowed(
        service.access.owned_run, "api", run_id, user_id, action="write"
    )
    return success_payload(await service.delete_run("api", run_id, user_id))


async def review_api_case_generate_task_run(
    run_id: str,
    body: AiGenerateTaskReviewRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationCandidateReview = Depends(get_generation_review),
):
    await ensure_legacy_mutation_allowed(service.owned_run, "api", run_id, user_id)
    return success_payload(
        await service.review(
            "api",
            run_id,
            body.model_dump(by_alias=True, exclude_none=True),
            user_id,
        )
    )


async def review_api_case_stage(
    run_id: str,
    body: AiGenerateTaskReviewRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationStageWorkflow = Depends(get_generation_stages),
):
    await ensure_legacy_mutation_allowed(service.owned_run, "api", run_id, user_id)
    return success_payload(
        await service.review_api_checkpoint(
            run_id, body.model_dump(by_alias=True, exclude_none=True), user_id
        )
    )


async def save_api_case_stage_output(
    run_id: str,
    body: AiGenerateTaskRunRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationStageWorkflow = Depends(get_generation_stages),
):
    await ensure_legacy_mutation_allowed(service.owned_run, "api", run_id, user_id, action="write")
    return success_payload(
        await service.save_api_checkpoint(
            run_id, body.model_dump(by_alias=True, exclude_none=True), user_id
        )
    )


async def revise_api_case_stage(
    run_id: str,
    body: AiGenerateTaskReviewRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationStageWorkflow = Depends(get_generation_stages),
):
    await ensure_legacy_mutation_allowed(
        service.owned_run, "api", run_id, user_id, action="execute"
    )
    return success_payload(
        await service.revise_api_stage(
            run_id, body.model_dump(by_alias=True, exclude_none=True), user_id
        )
    )


async def retry_api_case_stage(
    run_id: str,
    body: AiGenerateTaskRunRequest | None = None,
    user_id: str = Depends(get_current_user_id),
    service: GenerationStageWorkflow = Depends(get_generation_stages),
):
    await ensure_legacy_mutation_allowed(
        service.owned_run, "api", run_id, user_id, action="execute"
    )
    return success_payload(
        await service.retry_api_stage(
            run_id, body.model_dump(by_alias=True, exclude_none=True) if body else {}, user_id
        )
    )


async def update_api_case_generate_task_run_result(
    run_id: str,
    body: AiGenerateTaskResultRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationCandidateReview = Depends(get_generation_review),
):
    await ensure_legacy_mutation_allowed(service.owned_run, "api", run_id, user_id, action="write")
    return success_payload(await service.update_result("api", run_id, body.result_yaml, user_id))


async def import_api_case_generate_task_run(
    run_id: str,
    body: AiGenerateTaskImportRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiCandidateImporter = Depends(get_generation_api_importer),
):
    await ensure_legacy_mutation_allowed(
        service.owned_run, "api", run_id, user_id, action="execute"
    )
    return success_payload(
        await service.import_api_run(
            run_id,
            body.collection_id,
            body.confirm_overwrite,
            user_id,
        )
    )
