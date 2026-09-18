from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from app.dependencies import (
    TestTaskServiceFactory,
    get_zentao_request_token,
    get_zentao_testtask_service_factory,
)
from app.schemas.response import Response, handle_success
from app.schemas.zentao.imports import (
    ImportListData,
    TestTaskImportData,
)
from app.schemas.zentao.query import ZentaoDetailQuery, ZentaoListQuery

router = APIRouter()

token_dependency = Annotated[str, Depends(get_zentao_request_token)]
service_factory_dependency = Annotated[
    TestTaskServiceFactory,
    Depends(get_zentao_testtask_service_factory),
]
execution_id_path = Annotated[int, Path(ge=1, description="Zentao execution ID")]
testtask_id_path = Annotated[int, Path(ge=1, description="Zentao test task ID")]
list_query_dependency = Annotated[ZentaoListQuery, Query()]
detail_query_dependency = Annotated[ZentaoDetailQuery, Query()]


@router.get(
    "/executions/{execution_id}/testtasks",
    response_model=Response[ImportListData[TestTaskImportData]],
    summary="Query Zentao test task list under an execution",
)
async def get_execution_testtasks(
    request: Request,
    execution_id: execution_id_path,
    query: list_query_dependency,
    token: token_dependency,
    service_factory: service_factory_dependency,
):
    service = service_factory(query.base_url, token)
    return handle_success(
        request,
        await service.list_testtasks(execution_id, query.to_service_query()),
    )


@router.get(
    "/testtasks/{testtask_id}",
    response_model=Response[TestTaskImportData],
    summary="Get Zentao test task detail",
)
async def get_testtask(
    request: Request,
    testtask_id: testtask_id_path,
    query: detail_query_dependency,
    token: token_dependency,
    service_factory: service_factory_dependency,
):
    service = service_factory(query.base_url, token)
    return handle_success(request, await service.get_testtask(testtask_id))
