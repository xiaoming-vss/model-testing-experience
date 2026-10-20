from __future__ import annotations

from fastapi import Depends, Query

from testing_agent.api.deps import (
    get_current_user_id,
    get_generation_archives,
    get_generation_import_context,
    get_generation_launcher,
    get_generation_queries,
    get_generation_review,
    get_generation_task_commands,
)
from testing_agent.core.errors import success_payload
from testing_agent.schemas.ai_generate_task import (
    AiGenerateTaskRequest,
    AiGenerateTaskResultRequest,
    AiGenerateTaskReviewRequest,
    AiGenerateTaskRunRequest,
    SourceArchiveAttachRequest,
    UiGenerateTaskImportRequest,
)
from testing_agent.services.ai_candidate_review import GenerationCandidateReview
from testing_agent.services.ai_run_launcher import GenerationRunLauncher
from testing_agent.services.ai_source_archive import SourceArchiveManager
from testing_agent.services.ai_task_access import CandidateImportContext
from testing_agent.services.ai_task_commands import GenerationTaskCommands
from testing_agent.services.ai_task_queries import GenerationQueries
from testing_agent.services.ui_generate_import import import_ui_run


async def create_ui_case_generate_task(
    project_id: str,
    body: AiGenerateTaskRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationTaskCommands = Depends(get_generation_task_commands),
):
    return success_payload(
        await service.create(
            "ui", project_id, body.model_dump(by_alias=True, exclude_none=True), user_id
        )
    )


async def list_ui_case_generate_tasks(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(await service.list("ui", project_id, user_id))


async def get_ui_case_generate_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(await service.get("ui", task_id, user_id))


async def update_ui_case_generate_task(
    task_id: str,
    body: AiGenerateTaskRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationTaskCommands = Depends(get_generation_task_commands),
):
    return success_payload(
        await service.update(
            "ui", task_id, body.model_dump(by_alias=True, exclude_none=True), user_id
        )
    )


async def delete_ui_case_generate_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationTaskCommands = Depends(get_generation_task_commands),
):
    return success_payload(await service.delete("ui", task_id, user_id))


async def upload_ui_case_source_archive(
    task_id: str,
    body: SourceArchiveAttachRequest,
    user_id: str = Depends(get_current_user_id),
    service: SourceArchiveManager = Depends(get_generation_archives),
):
    return success_payload(await service.upload_source_archive(task_id, body.file_id, user_id))


async def run_ui_case_generate_task(
    task_id: str,
    body: AiGenerateTaskRunRequest | None = None,
    user_id: str = Depends(get_current_user_id),
    service: GenerationRunLauncher = Depends(get_generation_launcher),
):
    payload = body.model_dump(by_alias=True, exclude_none=True) if body else None
    return success_payload(await service.launch("ui", task_id, payload, user_id))


async def list_ui_case_generate_task_runs(
    task_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(
        await service.list_run_summaries("ui", task_id, user_id, page, page_size)
    )


async def get_ui_case_generate_task_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(await service.get_run("ui", run_id, user_id))


async def delete_ui_case_generate_task_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationTaskCommands = Depends(get_generation_task_commands),
):
    return success_payload(await service.delete_run("ui", run_id, user_id))


async def update_ui_case_generate_task_run_result(
    run_id: str,
    body: AiGenerateTaskResultRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationCandidateReview = Depends(get_generation_review),
):
    return success_payload(await service.update_result("ui", run_id, body.result_yaml, user_id))


async def review_ui_case_generate_task_run(
    run_id: str,
    body: AiGenerateTaskReviewRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationCandidateReview = Depends(get_generation_review),
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
    service: CandidateImportContext = Depends(get_generation_import_context),
):
    return success_payload(
        await import_ui_run(service, run_id, body.suite_id, body.confirm_overwrite, user_id)
    )
