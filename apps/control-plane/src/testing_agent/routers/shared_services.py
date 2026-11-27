from fastapi import APIRouter

from testing_agent.handlers.shared_service import (
    authorize_service,
    create_service,
    delete_service,
    list_services,
    list_templates,
    rename_service,
    revoke_authorization,
)
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse
from testing_agent.schemas.shared_service import McpTemplate, SharedServiceResponse

router = APIRouter(prefix="/projects/{project_id}/services/{provider}")

router.get("", response_model=ApiResponse[ListResponse[SharedServiceResponse]])(list_services)
router.get("/templates", response_model=ApiResponse[ListResponse[McpTemplate]])(list_templates)
router.post("", response_model=ApiResponse[SharedServiceResponse])(create_service)
router.patch("/{service_id}", response_model=ApiResponse[SharedServiceResponse])(rename_service)
router.delete("/{service_id}", response_model=ApiResponse[EmptyData])(delete_service)
router.put("/{service_id}/authorization", response_model=ApiResponse[SharedServiceResponse])(
    authorize_service
)
router.delete("/{service_id}/authorization", response_model=ApiResponse[SharedServiceResponse])(
    revoke_authorization
)
