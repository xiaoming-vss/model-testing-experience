from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import get_ai_generate_task_service, get_current_user_id
from testing_agent.core.errors import success_payload
from testing_agent.schemas.ai_generate_task import (
    CodeRiskAnalysisRunRequest,
    CodeRiskAnalysisTaskRequest,
)
from testing_agent.services.ai_generate_task import AiGenerateTaskService
from testing_agent.services.code_risk_analysis import dump_code_risk_analysis_run


async def create_code_risk_analysis_task(
    project_id: str,
    body: CodeRiskAnalysisTaskRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
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
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.list("code_risk_analysis", project_id, user_id))


async def get_code_risk_analysis_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
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
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.list_runs("code_risk_analysis", task_id, user_id))


async def get_code_risk_analysis_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    run = await service.owned_run(user_id, run_id, "code_risk_analysis")
    return success_payload(dump_code_risk_analysis_run(run))


async def delete_code_risk_analysis_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.delete_run("code_risk_analysis", run_id, user_id))


async def delete_code_risk_analysis_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.delete("code_risk_analysis", task_id, user_id))
