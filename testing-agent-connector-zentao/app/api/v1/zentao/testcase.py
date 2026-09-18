from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Query, Request

from app.dependencies import (
    TestCaseServiceFactory,
    get_zentao_request_token,
    get_zentao_testcase_service_factory,
)
from app.schemas.response import Response, handle_success
from app.schemas.zentao.imports import ImportListData
from app.schemas.zentao.query import ZentaoDetailQuery, ZentaoListQuery
from app.schemas.zentao.testcase import (
    TestCaseBatchCreateData,
    TestCaseBatchCreateRequest,
    TestCaseImportData,
)

router = APIRouter()

token_dependency = Annotated[str, Depends(get_zentao_request_token)]
service_factory_dependency = Annotated[
    TestCaseServiceFactory,
    Depends(get_zentao_testcase_service_factory),
]
execution_id_path = Annotated[int, Path(ge=1, description="Zentao execution ID")]
list_query_dependency = Annotated[ZentaoListQuery, Query()]
detail_query_dependency = Annotated[ZentaoDetailQuery, Query()]
create_payload_dependency = Annotated[TestCaseBatchCreateRequest, Body()]


@router.post(
    "/testcases",
    response_model=Response[TestCaseBatchCreateData],
    summary="Create Zentao testcases",
)
async def create_testcases(
    request: Request,
    payload: create_payload_dependency,
    query: detail_query_dependency,
    token: token_dependency,
    service_factory: service_factory_dependency,
):
    service = service_factory(query.base_url, token)
    return handle_success(request, await service.create_testcases(payload))


@router.get(
    "/executions/{execution_id}/cases",
    response_model=Response[ImportListData[TestCaseImportData]],
    summary="Query Zentao testcase details under an execution",
)
async def get_execution_cases(
    request: Request,
    execution_id: execution_id_path,
    query: list_query_dependency,
    token: token_dependency,
    service_factory: service_factory_dependency,
):
    service = service_factory(query.base_url, token)
    return handle_success(
        request,
        await service.list_execution_cases(execution_id, query.to_service_query()),
    )
