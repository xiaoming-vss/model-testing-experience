from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import get_ai_generate_task_service, get_current_user_id
from testing_agent.core.errors import success_payload
from testing_agent.schemas.ai_generate_task import (
    AiGenerateTaskReviewRequest,
    RequirementAnalysisRunRequest,
    RequirementAnalysisTaskRequest,
)
from testing_agent.services.ai_generate_task import AiGenerateTaskService, dump_run


async def create_requirement_analysis_task(
    project_id: str,
    body: RequirementAnalysisTaskRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
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
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.list("requirement_analysis", project_id, user_id))


async def get_requirement_analysis_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.get("requirement_analysis", task_id, user_id))


async def update_requirement_analysis_task(
    task_id: str,
    body: RequirementAnalysisTaskRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
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
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.delete("requirement_analysis", task_id, user_id))


async def run_requirement_analysis_task(
    task_id: str,
    body: RequirementAnalysisRunRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await service.run(
            "requirement_analysis",
            task_id,
            body.model_dump(by_alias=True, exclude_none=True),
            user_id,
        )
    )


async def list_requirement_analysis_task_runs(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.list_runs("requirement_analysis", task_id, user_id))


async def get_requirement_analysis_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        dump_run(await service.owned_run(user_id, run_id, "requirement_analysis"))
    )


async def delete_requirement_analysis_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.delete_run("requirement_analysis", run_id, user_id))


async def save_requirement_analysis_stage_output(
    run_id: str,
    body: RequirementAnalysisRunRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await service.save_requirement_analysis_stage_output(
            run_id, body.model_dump(by_alias=True, exclude_none=True), user_id
        )
    )


async def review_requirement_analysis_stage(
    run_id: str,
    body: AiGenerateTaskReviewRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await service.review_requirement_analysis_stage(
            run_id, body.model_dump(by_alias=True, exclude_none=True), user_id
        )
    )


async def revise_requirement_analysis_stage(
    run_id: str,
    body: AiGenerateTaskReviewRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await service.revise_requirement_analysis_stage(
            run_id, body.model_dump(by_alias=True, exclude_none=True), user_id
        )
    )


async def import_requirement_analysis_run_to_requirement(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.import_requirement_analysis_run(run_id, user_id))


async def retry_requirement_analysis_stage(
    run_id: str,
    body: AiGenerateTaskReviewRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await service.retry_stage(
            run_id,
            body.model_dump(by_alias=True, exclude_none=True),
            user_id,
            kind="requirement_analysis",
        )
    )
