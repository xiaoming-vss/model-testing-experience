from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from app.dependencies import (
    ExecutionServiceFactory,
    get_zentao_execution_service_factory,
    get_zentao_request_token,
)
from app.schemas.response import Response, handle_success
from app.schemas.zentao.imports import (
    ExecutionImportData,
    ImportListData,
    StoryImportData,
)
from app.schemas.zentao.query import ZentaoDetailQuery, ZentaoListQuery

router = APIRouter()

token_dependency = Annotated[str, Depends(get_zentao_request_token)]
service_factory_dependency = Annotated[
    ExecutionServiceFactory,
    Depends(get_zentao_execution_service_factory),
]
project_id_path = Annotated[int, Path(ge=1, description="Zentao project ID")]
execution_id_path = Annotated[int, Path(ge=1, description="Zentao execution ID")]
list_query_dependency = Annotated[ZentaoListQuery, Query()]
detail_query_dependency = Annotated[ZentaoDetailQuery, Query()]


@router.get(
    "/projects/{project_id}/executions",
    response_model=Response[ImportListData[ExecutionImportData]],
    summary="Query Zentao execution list under a project",
)
async def get_project_executions(
    request: Request,
    project_id: project_id_path,
    query: list_query_dependency,
    token: token_dependency,
    service_factory: service_factory_dependency,
):
    service = service_factory(query.base_url, token)
    return handle_success(
        request,
        await service.list_executions(project_id, query.to_service_query()),
    )


@router.get(
    "/executions/{execution_id}",
    response_model=Response[ExecutionImportData],
    summary="Get Zentao execution detail",
)
async def get_execution(
    request: Request,
    execution_id: execution_id_path,
    query: detail_query_dependency,
    token: token_dependency,
    service_factory: service_factory_dependency,
):
    service = service_factory(query.base_url, token)
    return handle_success(request, await service.get_execution(execution_id))


@router.get(
    "/executions/{execution_id}/stories",
    response_model=Response[ImportListData[StoryImportData]],
    summary="Query Zentao stories under an execution",
)
async def get_execution_stories(
    request: Request,
    execution_id: execution_id_path,
    query: detail_query_dependency,
    token: token_dependency,
    service_factory: service_factory_dependency,
):
    service = service_factory(query.base_url, token)
    return handle_success(request, await service.list_execution_stories(execution_id))
