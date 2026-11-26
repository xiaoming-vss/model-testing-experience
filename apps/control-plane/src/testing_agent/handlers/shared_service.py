"""Project shared-service management; routers only map HTTP paths."""

from fastapi import Depends

from testing_agent.api.deps import get_current_user_id, get_shared_service
from testing_agent.core.errors import success_payload
from testing_agent.schemas.shared_service import (
    PersonalAuthorizationRequest,
    Provider,
    ServiceCreate,
    ServiceRename,
)
from testing_agent.services.shared_service import SharedServiceService


async def list_services(
    project_id: str,
    provider: Provider,
    user_id: str = Depends(get_current_user_id),
    services: SharedServiceService = Depends(get_shared_service),
):
    return success_payload(await services.list(user_id, project_id, provider))


async def list_templates(
    project_id: str,
    provider: Provider,
    user_id: str = Depends(get_current_user_id),
    services: SharedServiceService = Depends(get_shared_service),
):
    return success_payload(await services.templates(user_id, project_id, provider))


async def create_service(
    project_id: str,
    provider: Provider,
    body: ServiceCreate,
    user_id: str = Depends(get_current_user_id),
    services: SharedServiceService = Depends(get_shared_service),
):
    return success_payload(await services.create(user_id, project_id, provider, body))


async def rename_service(
    project_id: str,
    provider: Provider,
    service_id: str,
    body: ServiceRename,
    user_id: str = Depends(get_current_user_id),
    services: SharedServiceService = Depends(get_shared_service),
):
    return success_payload(
        await services.rename(
            user_id,
            project_id,
            provider,
            service_id,
            body.name,
            body.zentao_instance_url,
            body.base_url,
            body.confirm_instance_switch,
            body.allow_http,
            body.insecure_skip_verify,
        )
    )


async def delete_service(
    project_id: str,
    provider: Provider,
    service_id: str,
    user_id: str = Depends(get_current_user_id),
    services: SharedServiceService = Depends(get_shared_service),
):
    return success_payload(await services.delete(user_id, project_id, provider, service_id))


async def authorize_service(
    project_id: str,
    provider: Provider,
    service_id: str,
    body: PersonalAuthorizationRequest,
    user_id: str = Depends(get_current_user_id),
    services: SharedServiceService = Depends(get_shared_service),
):
    return success_payload(
        await services.authorize(user_id, project_id, provider, service_id, body)
    )


async def revoke_authorization(
    project_id: str,
    provider: Provider,
    service_id: str,
    user_id: str = Depends(get_current_user_id),
    services: SharedServiceService = Depends(get_shared_service),
):
    return success_payload(await services.revoke(user_id, project_id, provider, service_id))
