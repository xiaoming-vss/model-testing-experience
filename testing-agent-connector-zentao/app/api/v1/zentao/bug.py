from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from app.dependencies import (
    BugServiceFactory,
    get_zentao_bug_service_factory,
    get_zentao_request_token,
)
from app.schemas.response import Response, handle_success
from app.schemas.zentao.bug import BugImportData
from app.schemas.zentao.imports import ImportListData
from app.schemas.zentao.query import ZentaoListQuery

router = APIRouter()

token_dependency = Annotated[str, Depends(get_zentao_request_token)]
service_factory_dependency = Annotated[
    BugServiceFactory,
    Depends(get_zentao_bug_service_factory),
]
execution_id_path = Annotated[int, Path(ge=1, description="Zentao execution ID")]
list_query_dependency = Annotated[ZentaoListQuery, Query()]


@router.get(
    "/executions/{execution_id}/bugs",
    response_model=Response[ImportListData[BugImportData]],
    summary="Query Zentao bug list under an execution",
)
async def get_execution_bugs(
    request: Request,
    execution_id: execution_id_path,
    query: list_query_dependency,
    token: token_dependency,
    service_factory: service_factory_dependency,
):
    service = service_factory(query.base_url, token)
    return handle_success(
        request,
        await service.list_execution_bugs(execution_id, query.to_service_query()),
    )
