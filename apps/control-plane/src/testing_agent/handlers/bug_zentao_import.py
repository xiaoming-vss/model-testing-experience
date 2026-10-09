"""禅道新建 Bug 导入入口：候选、预览、导入，全部要求项目写权限。"""

from fastapi import Depends, Query

from testing_agent.api.deps import (
    get_bug_service,
    get_current_user_id,
    get_integration_connection_service,
)
from testing_agent.core.errors import success_payload
from testing_agent.schemas.bug_zentao_import import (
    ZentaoBugImportPreviewRequest,
    ZentaoBugImportRequest,
)
from testing_agent.services.bug import BugService
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.zentao_bug_import import ZentaoBugImportService


def service(
    bugs: BugService = Depends(get_bug_service),
    connections: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return ZentaoBugImportService(bugs, connections)


async def list_zentao_bug_candidates(
    project_id: str,
    sprint_id: str = Query(default="", alias="sprintId", max_length=64),
    status: str = Query(default="", max_length=100),
    keyword: str = Query(default="", max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    imports: ZentaoBugImportService = Depends(service),
):
    data = await imports.candidates(
        user_id,
        project_id,
        sprint_id=sprint_id,
        status=status,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return success_payload(data)


async def preview_zentao_bug_import(
    project_id: str,
    body: ZentaoBugImportPreviewRequest,
    user_id: str = Depends(get_current_user_id),
    imports: ZentaoBugImportService = Depends(service),
):
    data = await imports.preview(user_id, project_id, body.remote_bug_ids)
    return success_payload(data)


async def import_zentao_bugs(
    project_id: str,
    body: ZentaoBugImportRequest,
    user_id: str = Depends(get_current_user_id),
    imports: ZentaoBugImportService = Depends(service),
):
    data = await imports.import_bugs(user_id, project_id, body.request_id, body.items)
    return success_payload(data)
