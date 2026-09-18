from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from app.dependencies import (
    ProjectServiceFactory,
    get_zentao_project_service_factory,
    get_zentao_request_token,
)
from app.schemas.response import Response, handle_success
from app.schemas.zentao.imports import (
    ImportListData,
    ProjectImportData,
)
from app.schemas.zentao.query import ZentaoDetailQuery, ZentaoListQuery

router = APIRouter()

token_dependency = Annotated[str, Depends(get_zentao_request_token)]
service_factory_dependency = Annotated[
    ProjectServiceFactory,
    Depends(get_zentao_project_service_factory),
]
project_id_path = Annotated[int, Path(ge=1, description="Zentao project ID")]
list_query_dependency = Annotated[ZentaoListQuery, Query()]
detail_query_dependency = Annotated[ZentaoDetailQuery, Query()]


@router.get(
    "/projects",
    response_model=Response[ImportListData[ProjectImportData]],
    summary="Query Zentao project list",
)
async def get_projects(
    request: Request,
    query: list_query_dependency,
    token: token_dependency,
    service_factory: service_factory_dependency,
):
    service = service_factory(query.base_url, token)
    return handle_success(request, await service.list_projects(query.to_service_query()))


@router.get(
    "/projects/{project_id}",
    response_model=Response[ProjectImportData],
    summary="Get Zentao project detail",
)
async def get_project(
    request: Request,
    project_id: project_id_path,
    query: detail_query_dependency,
    token: token_dependency,
    service_factory: service_factory_dependency,
):
    service = service_factory(query.base_url, token)
    return handle_success(request, await service.get_project(project_id))
