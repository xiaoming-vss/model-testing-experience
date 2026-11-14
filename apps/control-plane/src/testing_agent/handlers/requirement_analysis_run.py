from __future__ import annotations

from fastapi import Depends, Query

from testing_agent.api.deps import (
    get_current_user_id,
    get_generation_launcher,
    get_generation_queries,
    get_generation_stages,
    get_generation_task_commands,
)
from testing_agent.core.errors import success_payload
from testing_agent.handlers.generation_guards import ensure_legacy_mutation_allowed
from testing_agent.schemas.ai_generate_task import (
    AiGenerateTaskReviewRequest,
    RequirementAnalysisRunRequest,
    RequirementAnalysisTaskRequest,
)
from testing_agent.services.ai_run_launcher import GenerationRunLauncher
from testing_agent.services.ai_stage_workflow import GenerationStageWorkflow
from testing_agent.services.ai_task_commands import GenerationTaskCommands
from testing_agent.services.ai_task_queries import GenerationQueries


async def create_requirement_analysis_task(
    project_id: str,
    body: RequirementAnalysisTaskRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationTaskCommands = Depends(get_generation_task_commands),
):
    return success_payload(
        await service.create(
            "requirement_analysis",
            project_id,
            body.model_dump(by_alias=True, exclude_none=True),
            user_id,
        )
    )


async def list_requirement_analysis_tasks(
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
            "requirement_analysis",
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


async def get_requirement_analysis_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(await service.get("requirement_analysis", task_id, user_id))


async def update_requirement_analysis_task(
    task_id: str,
    body: RequirementAnalysisTaskRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationTaskCommands = Depends(get_generation_task_commands),
):
    return success_payload(
        await service.update(
            "requirement_analysis",
            task_id,
            body.model_dump(by_alias=True, exclude_none=True),
            user_id,
        )
    )


async def delete_requirement_analysis_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationTaskCommands = Depends(get_generation_task_commands),
):
    return success_payload(await service.delete("requirement_analysis", task_id, user_id))


async def run_requirement_analysis_task(
    task_id: str,
    body: RequirementAnalysisRunRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationRunLauncher = Depends(get_generation_launcher),
):
    return success_payload(
        await service.launch(
            "requirement_analysis",
            task_id,
            body.model_dump(by_alias=True, exclude_none=True),
            user_id,
        )
    )


async def list_requirement_analysis_task_runs(
    task_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(
        await service.list_run_summaries("requirement_analysis", task_id, user_id, page, page_size)
    )


async def get_requirement_analysis_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(await service.get_run("requirement_analysis", run_id, user_id))


async def delete_requirement_analysis_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationTaskCommands = Depends(get_generation_task_commands),
):
    await ensure_legacy_mutation_allowed(
        service.access.owned_run, "requirement_analysis", run_id, user_id, action="write"
    )
    return success_payload(await service.delete_run("requirement_analysis", run_id, user_id))


async def save_requirement_analysis_stage_output(
    run_id: str,
    body: RequirementAnalysisRunRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationStageWorkflow = Depends(get_generation_stages),
):
    await ensure_legacy_mutation_allowed(service.owned_run, "requirement_analysis", run_id, user_id)
    return success_payload(
        await service.save_requirement_analysis_stage_output(
            run_id, body.model_dump(by_alias=True, exclude_none=True), user_id
        )
    )


async def review_requirement_analysis_stage(
    run_id: str,
    body: AiGenerateTaskReviewRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationStageWorkflow = Depends(get_generation_stages),
):
    await ensure_legacy_mutation_allowed(service.owned_run, "requirement_analysis", run_id, user_id)
    return success_payload(
        await service.review_requirement_analysis_stage(
            run_id, body.model_dump(by_alias=True, exclude_none=True), user_id
        )
    )


async def revise_requirement_analysis_stage(
    run_id: str,
    body: AiGenerateTaskReviewRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationStageWorkflow = Depends(get_generation_stages),
):
    await ensure_legacy_mutation_allowed(
        service.owned_run, "requirement_analysis", run_id, user_id, action="execute"
    )
    return success_payload(
        await service.revise_requirement_analysis_stage(
            run_id, body.model_dump(by_alias=True, exclude_none=True), user_id
        )
    )


async def retry_requirement_analysis_stage(
    run_id: str,
    body: AiGenerateTaskReviewRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationStageWorkflow = Depends(get_generation_stages),
):
    await ensure_legacy_mutation_allowed(
        service.owned_run, "requirement_analysis", run_id, user_id, action="execute"
    )
    return success_payload(
        await service.retry_stage(
            run_id,
            body.model_dump(by_alias=True, exclude_none=True),
            user_id,
            kind="requirement_analysis",
        )
    )
