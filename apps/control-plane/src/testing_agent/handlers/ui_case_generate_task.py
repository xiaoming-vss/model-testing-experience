from __future__ import annotations

from fastapi import Depends, File, UploadFile

from testing_agent.api.deps import get_ai_generate_task_service, get_current_user_id
from testing_agent.core.errors import success_payload
from testing_agent.schemas.ai_generate_task import (
    AiGenerateTaskRequest,
    AiGenerateTaskResultRequest,
    AiGenerateTaskReviewRequest,
    AiGenerateTaskRunRequest,
    UiGenerateTaskImportRequest,
)
from testing_agent.services.ai_generate_task import (
    MAX_SOURCE_ARCHIVE_BYTES,
    AiGenerateTaskService,
    dump_run,
)


async def create_ui_case_generate_task(
    project_id: str,
    body: AiGenerateTaskRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await service.create(
            "ui", project_id, body.model_dump(by_alias=True, exclude_none=True), user_id
        )
    )


async def list_ui_case_generate_tasks(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.list("ui", project_id, user_id))


async def get_ui_case_generate_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.get("ui", task_id, user_id))


async def update_ui_case_generate_task(
    task_id: str,
    body: AiGenerateTaskRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await service.update(
            "ui", task_id, body.model_dump(by_alias=True, exclude_none=True), user_id
        )
    )


async def delete_ui_case_generate_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.delete("ui", task_id, user_id))


async def upload_ui_case_source_archive(
    task_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await service.upload_source_archive(
            task_id, file.filename or "", await file.read(MAX_SOURCE_ARCHIVE_BYTES + 1), user_id
        )
    )


async def run_ui_case_generate_task(
    task_id: str,
    body: AiGenerateTaskRunRequest | None = None,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    payload = body.model_dump(by_alias=True, exclude_none=True) if body else None
    return success_payload(await service.run("ui", task_id, payload, user_id))


async def list_ui_case_generate_task_runs(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.list_runs("ui", task_id, user_id))


async def get_ui_case_generate_task_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(dump_run(await service.owned_run(user_id, run_id, "ui")))


async def update_ui_case_generate_task_run_result(
    run_id: str,
    body: AiGenerateTaskResultRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.update_result("ui", run_id, body.result_yaml, user_id))


async def review_ui_case_generate_task_run(
    run_id: str,
    body: AiGenerateTaskReviewRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await service.review(
            "ui", run_id, body.model_dump(by_alias=True, exclude_none=True), user_id
        )
    )


async def import_ui_case_generate_task_run(
    run_id: str,
    body: UiGenerateTaskImportRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await service.import_ui_run(run_id, body.suite_id, body.confirm_overwrite, user_id)
    )
