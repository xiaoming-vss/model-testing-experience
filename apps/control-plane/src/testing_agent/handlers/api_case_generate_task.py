from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import get_ai_generate_task_service, get_current_user_id
from testing_agent.core.errors import success_payload
from testing_agent.schemas.ai_generate_task import (
    AiGenerateTaskImportRequest,
    AiGenerateTaskRequest,
    AiGenerateTaskResultRequest,
    AiGenerateTaskReviewRequest,
    AiGenerateTaskRunRequest,
)
from testing_agent.services.ai_generate_task import AiGenerateTaskService, dump_run


async def create_api_case_generate_task(
    project_id: str,
    body: AiGenerateTaskRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
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
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.list("api", project_id, user_id))


async def get_api_case_generate_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.get("api", task_id, user_id))


async def update_api_case_generate_task(
    task_id: str,
    body: AiGenerateTaskRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
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
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.delete("api", task_id, user_id))


async def run_api_case_generate_task(
    task_id: str,
    body: AiGenerateTaskRunRequest | None = None,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    payload = body.model_dump(by_alias=True, exclude_none=True) if body else None
    return success_payload(await service.run("api", task_id, payload, user_id))


async def list_api_case_generate_task_runs(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.list_runs("api", task_id, user_id))


async def get_api_case_generate_task_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(dump_run(await service.owned_run(user_id, run_id, "api")))


async def delete_api_case_generate_task_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.delete_run("api", run_id, user_id))


async def review_api_case_generate_task_run(
    run_id: str,
    body: AiGenerateTaskReviewRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await service.review(
            "api",
            run_id,
            body.model_dump(by_alias=True, exclude_none=True),
            user_id,
        )
    )


async def update_api_case_generate_task_run_result(
    run_id: str,
    body: AiGenerateTaskResultRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.update_result("api", run_id, body.result_yaml, user_id))


async def import_api_case_generate_task_run(
    run_id: str,
    body: AiGenerateTaskImportRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await service.import_api_run(
            run_id,
            body.collection_id,
            body.confirm_overwrite,
            user_id,
        )
    )
