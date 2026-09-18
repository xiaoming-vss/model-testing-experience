from fastapi import APIRouter, Depends

from testing_agent.api.deps import get_current_user_id, get_integration_connection_service
from testing_agent.core.errors import success_payload
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse
from testing_agent.schemas.shared_service import (
    PersonalAuthorizationRequest,
    Provider,
    ServiceCreate,
    ServiceRename,
    SharedServiceResponse,
)
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.shared_service import SharedServiceService

router = APIRouter(prefix="/projects/{project_id}/services/{provider}")


def service(
    connections: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return SharedServiceService(connections)


@router.get("", response_model=ApiResponse[ListResponse[SharedServiceResponse]])
async def list_services(
    project_id: str,
    provider: Provider,
    user_id: str = Depends(get_current_user_id),
    services: SharedServiceService = Depends(service),
):
    return success_payload(await services.list(user_id, project_id, provider))


@router.post("", response_model=ApiResponse[SharedServiceResponse])
async def create_service(
    project_id: str,
    provider: Provider,
    body: ServiceCreate,
    user_id: str = Depends(get_current_user_id),
    services: SharedServiceService = Depends(service),
):
    return success_payload(await services.create(user_id, project_id, provider, body))


@router.patch("/{service_id}", response_model=ApiResponse[SharedServiceResponse])
async def rename_service(
    project_id: str,
    provider: Provider,
    service_id: str,
    body: ServiceRename,
    user_id: str = Depends(get_current_user_id),
    services: SharedServiceService = Depends(service),
):
    return success_payload(
        await services.rename(user_id, project_id, provider, service_id, body.name)
    )


@router.delete("/{service_id}", response_model=ApiResponse[EmptyData])
async def delete_service(
    project_id: str,
    provider: Provider,
    service_id: str,
    user_id: str = Depends(get_current_user_id),
    services: SharedServiceService = Depends(service),
):
    return success_payload(await services.delete(user_id, project_id, provider, service_id))


@router.put("/{service_id}/authorization", response_model=ApiResponse[SharedServiceResponse])
async def authorize_service(
    project_id: str,
    provider: Provider,
    service_id: str,
    body: PersonalAuthorizationRequest,
    user_id: str = Depends(get_current_user_id),
    services: SharedServiceService = Depends(service),
):
    return success_payload(
        await services.authorize(user_id, project_id, provider, service_id, body)
    )


@router.delete("/{service_id}/authorization", response_model=ApiResponse[SharedServiceResponse])
async def revoke_authorization(
    project_id: str,
    provider: Provider,
    service_id: str,
    user_id: str = Depends(get_current_user_id),
    services: SharedServiceService = Depends(service),
):
    return success_payload(await services.revoke(user_id, project_id, provider, service_id))
