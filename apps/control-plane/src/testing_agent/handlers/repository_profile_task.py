from __future__ import annotations

from fastapi import Depends, Query

from testing_agent.api.deps import (
    get_current_user_id,
    get_generation_launcher,
    get_generation_queries,
    get_generation_task_commands,
)
from testing_agent.core.errors import success_payload
from testing_agent.schemas.ai_generate_task import (
    RepositoryProfileRunRequest,
    RepositoryProfileTaskRequest,
)
from testing_agent.services.ai_run_launcher import GenerationRunLauncher
from testing_agent.services.ai_task_commands import GenerationTaskCommands
from testing_agent.services.ai_task_queries import GenerationQueries


async def create_repository_profile_task(
    project_id: str,
    body: RepositoryProfileTaskRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationTaskCommands = Depends(get_generation_task_commands),
):
    return success_payload(
        await service.create(
            "repository_profile",
            project_id,
            body.model_dump(by_alias=True, exclude_none=True),
            user_id,
        )
    )


async def list_repository_profile_tasks(
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
            "repository_profile",
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


async def run_repository_profile_task(
    task_id: str,
    body: RepositoryProfileRunRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationRunLauncher = Depends(get_generation_launcher),
):
    return success_payload(
        await service.launch(
            "repository_profile",
            task_id,
            body.model_dump(by_alias=True, exclude_none=True),
            user_id,
        )
    )


async def list_repository_profile_task_runs(
    task_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(
        await service.list_run_summaries("repository_profile", task_id, user_id, page, page_size)
    )


async def list_repository_profile_task_versions(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(await service.list_profile_versions(task_id, user_id))


async def get_repository_profile_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(await service.get_run("repository_profile", run_id, user_id))
