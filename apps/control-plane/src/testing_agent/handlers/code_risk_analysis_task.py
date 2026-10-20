from __future__ import annotations

from fastapi import Depends, Query

from testing_agent.api.deps import (
    get_ai_generate_task_service,
    get_current_user_id,
    get_generation_queries,
    get_generation_task_commands,
)
from testing_agent.core.errors import success_payload
from testing_agent.schemas.ai_generate_task import (
    CodeRiskAnalysisRunRequest,
    CodeRiskAnalysisTaskRequest,
)
from testing_agent.services.ai_generate_task import AiGenerateTaskService
from testing_agent.services.ai_task_commands import GenerationTaskCommands
from testing_agent.services.ai_task_queries import GenerationQueries


async def create_code_risk_analysis_task(
    project_id: str,
    body: CodeRiskAnalysisTaskRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationTaskCommands = Depends(get_generation_task_commands),
):
    return success_payload(
        await service.create(
            "code_risk_analysis",
            project_id,
            body.model_dump(by_alias=True, exclude_none=True),
            user_id,
        )
    )


async def list_code_risk_analysis_tasks(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(await service.list("code_risk_analysis", project_id, user_id))


async def get_code_risk_analysis_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(await service.get("code_risk_analysis", task_id, user_id))


async def run_code_risk_analysis_task(
    task_id: str,
    body: CodeRiskAnalysisRunRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await service.run(
            "code_risk_analysis",
            task_id,
            body.model_dump(by_alias=True, exclude_none=True),
            user_id,
        )
    )


async def list_code_risk_analysis_task_runs(
    task_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(
        await service.list_run_summaries("code_risk_analysis", task_id, user_id, page, page_size)
    )


async def get_code_risk_analysis_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(await service.get_run("code_risk_analysis", run_id, user_id))


async def delete_code_risk_analysis_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationTaskCommands = Depends(get_generation_task_commands),
):
    return success_payload(await service.delete_run("code_risk_analysis", run_id, user_id))


async def delete_code_risk_analysis_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationTaskCommands = Depends(get_generation_task_commands),
):
    return success_payload(await service.delete("code_risk_analysis", task_id, user_id))
