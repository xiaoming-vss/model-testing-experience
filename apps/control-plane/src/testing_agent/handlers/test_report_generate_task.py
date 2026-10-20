from __future__ import annotations

from fastapi import Depends, Query
from fastapi.responses import Response

from testing_agent.api.deps import (
    get_current_user_id,
    get_generation_queries,
    get_generation_reports,
)
from testing_agent.core.errors import success_payload
from testing_agent.schemas.ai_generate_task import TestReportGenerateTaskRunRequest
from testing_agent.services.ai_report import TestReportWorkflow
from testing_agent.services.ai_task_queries import GenerationQueries


async def run_test_report_generate_run(
    project_id: str,
    body: TestReportGenerateTaskRunRequest,
    user_id: str = Depends(get_current_user_id),
    service: TestReportWorkflow = Depends(get_generation_reports),
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
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(
        await service.list_test_report_run_summaries(
            project_id, sprint_id, user_id, page, page_size
        )
    )


async def get_test_report_generate_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(await service.get_run("test_report", run_id, user_id))


async def export_test_report_generate_run_pdf(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: TestReportWorkflow = Depends(get_generation_reports),
):
    content, filename = await service.export_test_report_pdf(run_id, user_id)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
