from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import get_ai_generate_task_service, get_current_user_id
from testing_agent.core.errors import success_payload
from testing_agent.schemas.ai_generate_task import (
    AiGenerateTaskRequest,
    AiGenerateTaskResultRequest,
    AiGenerateTaskReviewRequest,
    AiGenerateTaskRunRequest,
    FunctionGenerateTaskImportRequest,
)
from testing_agent.services.ai_generate_task import AiGenerateTaskService, dump_run
from testing_agent.services.function_generate_import import import_function_run


async def create_function_case_generate_task(
    project_id: str,
    body: AiGenerateTaskRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await service.create(
            "function", project_id, body.model_dump(by_alias=True, exclude_none=True), user_id
        )
    )


async def list_function_case_generate_tasks(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.list("function", project_id, user_id))


async def get_function_case_generate_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.get("function", task_id, user_id))


async def update_function_case_generate_task(
    task_id: str,
    body: AiGenerateTaskRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await service.update(
            "function", task_id, body.model_dump(by_alias=True, exclude_none=True), user_id
        )
    )


async def delete_function_case_generate_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.delete("function", task_id, user_id))


async def run_function_case_generate_task(
    task_id: str,
    body: AiGenerateTaskRunRequest | None = None,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    payload = body.model_dump(by_alias=True, exclude_none=True) if body else None
    return success_payload(await service.run("function", task_id, payload, user_id))


async def list_function_case_generate_task_runs(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.list_runs("function", task_id, user_id))


async def get_function_case_generate_task_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(dump_run(await service.owned_run(user_id, run_id, "function")))


async def delete_function_case_generate_task_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.delete_run("function", run_id, user_id))


async def save_function_case_stage_output(
    run_id: str,
    body: AiGenerateTaskRunRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await service.save_stage_output(
            run_id, body.model_dump(by_alias=True, exclude_none=True), user_id
        )
    )


async def review_function_case_stage(
    run_id: str,
    body: AiGenerateTaskReviewRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await service.review_stage(
            run_id,
            body.model_dump(by_alias=True, exclude_none=True),
            user_id,
        )
    )


async def retry_function_case_stage(
    run_id: str,
    body: AiGenerateTaskRunRequest | None = None,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    payload = body.model_dump(by_alias=True, exclude_none=True) if body else None
    return success_payload(await service.retry_stage(run_id, payload, user_id))


async def review_function_case_generate_task_run(
    run_id: str,
    body: AiGenerateTaskReviewRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await service.review(
            "function", run_id, body.model_dump(by_alias=True, exclude_none=True), user_id
        )
    )


async def update_function_case_generate_task_run_result(
    run_id: str,
    body: AiGenerateTaskResultRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await service.update_result("function", run_id, body.result_yaml, user_id)
    )


async def import_function_case_generate_task_run(
    run_id: str,
    body: FunctionGenerateTaskImportRequest | None = None,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await import_function_run(
            service,
            run_id,
            body.confirm_overwrite if body else False,
            user_id,
        )
    )


async def revise_function_case_stage(
    run_id: str,
    body: AiGenerateTaskReviewRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await service.revise_function_case_stage(
            run_id, body.model_dump(by_alias=True, exclude_none=True), user_id
        )
    )


async def generate_function_case_relation_analysis(
    run_id: str,
    body: AiGenerateTaskRunRequest | None = None,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    payload = body.model_dump(by_alias=True, exclude_none=True) if body else None
    return success_payload(await service.generate_relation_analysis(run_id, payload, user_id))
