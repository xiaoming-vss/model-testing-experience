from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.api_interface import (
    commit_api_interface_import,
    create_api_interface,
    create_api_interface_group,
    delete_api_interface,
    delete_api_interface_group,
    get_api_interface,
    list_project_api_interfaces,
    list_software_repository_api_interfaces,
    move_api_interface_group,
    preview_api_interface_import,
    rename_api_interface_group,
    update_api_interface,
)
from testing_agent.handlers.software_repository import (
    create_software_repository,
    delete_software_repository,
    get_software_repository,
    list_software_repositories,
    update_software_repository,
)
from testing_agent.handlers.ui_element import (
    create_ui_element,
    create_ui_element_group,
    delete_ui_element,
    delete_ui_element_group,
    get_ui_element,
    list_ui_element_groups,
    list_ui_elements,
    update_ui_element,
)
from testing_agent.schemas.api_interface import (
    ApiInterfaceGroupMutationResponse,
    ApiInterfaceListItem,
    ApiInterfaceResponse,
)
from testing_agent.schemas.api_interface_import import (
    ApiInterfaceImportCommitResponse,
    ApiInterfaceImportPreviewResponse,
)
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse
from testing_agent.schemas.software_repository import SoftwareRepositoryResponse
from testing_agent.schemas.ui_element import UiElementDetail, UiElementGroupView, UiElementSummary

router = APIRouter()

router.get(
    "/projects/{project_id}/software-repositories",
    response_model=ApiResponse[ListResponse[SoftwareRepositoryResponse]],
)(list_software_repositories)
router.post(
    "/projects/{project_id}/software-repositories",
    response_model=ApiResponse[SoftwareRepositoryResponse],
)(create_software_repository)
router.get(
    "/software-repositories/{software_repository_id}",
    response_model=ApiResponse[SoftwareRepositoryResponse],
)(get_software_repository)
router.patch(
    "/software-repositories/{software_repository_id}",
    response_model=ApiResponse[SoftwareRepositoryResponse],
)(update_software_repository)
router.delete(
    "/software-repositories/{software_repository_id}",
    response_model=ApiResponse[EmptyData],
)(delete_software_repository)

router.get(
    "/projects/{project_id}/api-interfaces",
    response_model=ApiResponse[ListResponse[ApiInterfaceListItem]],
)(list_project_api_interfaces)
router.get(
    "/software-repositories/{software_repository_id}/interfaces",
    response_model=ApiResponse[ListResponse[ApiInterfaceListItem]],
)(list_software_repository_api_interfaces)
router.post(
    "/software-repositories/{software_repository_id}/interfaces",
    response_model=ApiResponse[ApiInterfaceResponse],
)(create_api_interface)
router.post(
    "/software-repositories/{software_repository_id}/interface-groups",
    response_model=ApiResponse[ApiInterfaceGroupMutationResponse],
)(create_api_interface_group)
router.post(
    "/software-repositories/{software_repository_id}/interface-groups/rename",
    response_model=ApiResponse[ApiInterfaceGroupMutationResponse],
)(rename_api_interface_group)
router.post(
    "/software-repositories/{software_repository_id}/interface-groups/delete",
    response_model=ApiResponse[ApiInterfaceGroupMutationResponse],
)(delete_api_interface_group)
router.get(
    "/api-interfaces/{interface_id}",
    response_model=ApiResponse[ApiInterfaceResponse],
)(get_api_interface)
router.patch(
    "/api-interfaces/{interface_id}",
    response_model=ApiResponse[ApiInterfaceResponse],
)(update_api_interface)
router.patch(
    "/api-interfaces/{interface_id}/group",
    response_model=ApiResponse[ApiInterfaceResponse],
)(move_api_interface_group)
router.delete(
    "/api-interfaces/{interface_id}",
    response_model=ApiResponse[EmptyData],
)(delete_api_interface)

router.post(
    "/software-repositories/{software_repository_id}/interfaces/import/preview",
    response_model=ApiResponse[ApiInterfaceImportPreviewResponse],
)(preview_api_interface_import)
router.post(
    "/software-repositories/{software_repository_id}/interfaces/import",
    response_model=ApiResponse[ApiInterfaceImportCommitResponse],
)(commit_api_interface_import)

router.get(
    "/software-repositories/{software_repository_id}/ui-element-groups",
    response_model=ApiResponse[ListResponse[UiElementGroupView]],
)(list_ui_element_groups)
router.post(
    "/software-repositories/{software_repository_id}/ui-element-groups",
    response_model=ApiResponse[UiElementGroupView],
)(create_ui_element_group)
router.delete("/ui-element-groups/{group_id}", response_model=ApiResponse[EmptyData])(
    delete_ui_element_group
)
router.get(
    "/software-repositories/{software_repository_id}/ui-elements",
    response_model=ApiResponse[ListResponse[UiElementSummary]],
)(list_ui_elements)
router.post(
    "/software-repositories/{software_repository_id}/ui-elements",
    response_model=ApiResponse[UiElementDetail],
)(create_ui_element)
router.get("/ui-elements/{element_id}", response_model=ApiResponse[UiElementDetail])(get_ui_element)
router.patch("/ui-elements/{element_id}", response_model=ApiResponse[UiElementDetail])(
    update_ui_element
)
router.delete("/ui-elements/{element_id}", response_model=ApiResponse[EmptyData])(delete_ui_element)
