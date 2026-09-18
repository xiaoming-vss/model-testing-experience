from __future__ import annotations

from fastapi import Depends, Query
from fastapi.responses import Response

from testing_agent.api.deps import get_ai_generate_task_service, get_current_user_id
from testing_agent.core.errors import success_payload
from testing_agent.schemas.ai_generate_task import TestReportGenerateTaskRunRequest
from testing_agent.services.ai_generate_task import AiGenerateTaskService, dump_run


async def run_test_report_generate_run(
    project_id: str,
    body: TestReportGenerateTaskRunRequest,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await service.run_test_report(
            project_id,
            body.model_dump(by_alias=True, exclude_none=True),
            user_id,
        )
    )


async def list_test_report_generate_runs(
    project_id: str,
    sprint_id: str = Query(alias="sprintId"),
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await service.list_test_report_runs(project_id, sprint_id, user_id))


async def get_test_report_generate_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(dump_run(await service.owned_run(user_id, run_id, "test_report")))


async def export_test_report_generate_run_pdf(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    content, filename = await service.export_test_report_pdf(run_id, user_id)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
