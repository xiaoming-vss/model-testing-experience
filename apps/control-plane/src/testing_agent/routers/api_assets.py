from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.api_app import (
    create_api_app,
    delete_api_app,
    get_api_app,
    list_api_apps,
    update_api_app,
)
from testing_agent.handlers.api_interface import (
    commit_api_interface_import,
    create_api_interface,
    delete_api_interface,
    get_api_interface,
    list_app_api_interfaces,
    list_project_api_interfaces,
    preview_api_interface_import,
    update_api_interface,
)
from testing_agent.schemas.api_app import ApiAppResponse
from testing_agent.schemas.api_interface import ApiInterfaceListItem, ApiInterfaceResponse
from testing_agent.schemas.api_interface_import import (
    ApiInterfaceImportCommitResponse,
    ApiInterfaceImportPreviewResponse,
)
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse

router = APIRouter()

router.get(
    "/projects/{project_id}/api-apps",
    response_model=ApiResponse[ListResponse[ApiAppResponse]],
)(list_api_apps)
router.post(
    "/projects/{project_id}/api-apps",
    response_model=ApiResponse[ApiAppResponse],
)(create_api_app)
router.get("/api-apps/{app_id}", response_model=ApiResponse[ApiAppResponse])(get_api_app)
router.patch("/api-apps/{app_id}", response_model=ApiResponse[ApiAppResponse])(update_api_app)
router.delete("/api-apps/{app_id}", response_model=ApiResponse[EmptyData])(delete_api_app)

router.get(
    "/projects/{project_id}/api-interfaces",
    response_model=ApiResponse[ListResponse[ApiInterfaceListItem]],
)(list_project_api_interfaces)
router.get(
    "/api-apps/{app_id}/interfaces",
    response_model=ApiResponse[ListResponse[ApiInterfaceListItem]],
)(list_app_api_interfaces)
router.post(
    "/api-apps/{app_id}/interfaces",
    response_model=ApiResponse[ApiInterfaceResponse],
)(create_api_interface)
router.get(
    "/api-interfaces/{interface_id}",
    response_model=ApiResponse[ApiInterfaceResponse],
)(get_api_interface)
router.patch(
    "/api-interfaces/{interface_id}",
    response_model=ApiResponse[ApiInterfaceResponse],
)(update_api_interface)
router.delete(
    "/api-interfaces/{interface_id}",
    response_model=ApiResponse[EmptyData],
)(delete_api_interface)

router.post(
    "/api-apps/{app_id}/interfaces/import/preview",
    response_model=ApiResponse[ApiInterfaceImportPreviewResponse],
)(preview_api_interface_import)
router.post(
    "/api-apps/{app_id}/interfaces/import",
    response_model=ApiResponse[ApiInterfaceImportCommitResponse],
)(commit_api_interface_import)
