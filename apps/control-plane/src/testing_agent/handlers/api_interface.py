from __future__ import annotations

from fastapi import Depends, File, Form, Query, UploadFile

from testing_agent.api.deps import (
    get_api_interface_import_service,
    get_api_interface_service,
    get_current_user_id,
)
from testing_agent.core.errors import success_payload
from testing_agent.domain.api_interface_query import ApiInterfaceQuery
from testing_agent.schemas.api_interface import (
    ApiInterfaceCreateRequest,
    ApiInterfaceGroupCreateRequest,
    ApiInterfaceGroupDeleteRequest,
    ApiInterfaceGroupRenameRequest,
    ApiInterfaceMoveGroupRequest,
    ApiInterfaceUpdateRequest,
)
from testing_agent.services.api_interface import ApiInterfaceService
from testing_agent.services.api_interface_import import ApiInterfaceImportService


async def create_api_interface(
    software_repository_id: str,
    body: ApiInterfaceCreateRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiInterfaceService = Depends(get_api_interface_service),
):
    return success_payload(await service.create(user_id, software_repository_id, body))


async def list_project_api_interfaces(
    project_id: str,
    software_repository_id: str = Query(default="", alias="softwareRepositoryId"),
    method: str = Query(default=""),
    requirement_id: str = Query(default="", alias="requirementId"),
    sprint_id: str = Query(default="", alias="sprintId"),
    keyword: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    service: ApiInterfaceService = Depends(get_api_interface_service),
):
    return success_payload(
        await service.list_project(
            user_id,
            ApiInterfaceQuery.for_page(
                project_id=project_id,
                page=page,
                page_size=page_size,
                software_repository_id=software_repository_id,
                method=method,
                requirement_id=requirement_id,
                sprint_id=sprint_id,
                keyword=keyword,
            ),
        )
    )


async def list_software_repository_api_interfaces(
    software_repository_id: str,
    method: str = Query(default=""),
    requirement_id: str = Query(default="", alias="requirementId"),
    sprint_id: str = Query(default="", alias="sprintId"),
    keyword: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    service: ApiInterfaceService = Depends(get_api_interface_service),
):
    return success_payload(
        await service.list_software_repository(
            user_id,
            software_repository_id,
            ApiInterfaceQuery.for_page(
                page=page,
                page_size=page_size,
                method=method,
                requirement_id=requirement_id,
                sprint_id=sprint_id,
                keyword=keyword,
            ),
        )
    )


async def get_api_interface(
    interface_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiInterfaceService = Depends(get_api_interface_service),
):
    return success_payload(await service.get(user_id, interface_id))


async def update_api_interface(
    interface_id: str,
    body: ApiInterfaceUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiInterfaceService = Depends(get_api_interface_service),
):
    return success_payload(await service.update(user_id, interface_id, body))


async def create_api_interface_group(
    software_repository_id: str,
    body: ApiInterfaceGroupCreateRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiInterfaceService = Depends(get_api_interface_service),
):
    return success_payload(await service.create_group(user_id, software_repository_id, body))


async def rename_api_interface_group(
    software_repository_id: str,
    body: ApiInterfaceGroupRenameRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiInterfaceService = Depends(get_api_interface_service),
):
    return success_payload(await service.rename_group(user_id, software_repository_id, body))


async def delete_api_interface_group(
    software_repository_id: str,
    body: ApiInterfaceGroupDeleteRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiInterfaceService = Depends(get_api_interface_service),
):
    return success_payload(await service.delete_group(user_id, software_repository_id, body))


async def move_api_interface_group(
    interface_id: str,
    body: ApiInterfaceMoveGroupRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiInterfaceService = Depends(get_api_interface_service),
):
    return success_payload(await service.move_to_group(user_id, interface_id, body))


async def delete_api_interface(
    interface_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiInterfaceService = Depends(get_api_interface_service),
):
    return success_payload(await service.delete(user_id, interface_id))


async def preview_api_interface_import(
    software_repository_id: str,
    file: UploadFile | None = File(default=None),
    user_id: str = Depends(get_current_user_id),
    service: ApiInterfaceImportService = Depends(get_api_interface_import_service),
):
    return success_payload(await service.preview(user_id, software_repository_id, file))


async def commit_api_interface_import(
    software_repository_id: str,
    source_digest: str = Form(..., alias="sourceDigest"),
    selected_keys: str = Form(..., alias="selectedKeys"),
    expected_items: str = Form(default="{}", alias="expectedItems"),
    apply_base_path: bool = Form(default=False, alias="applyBasePath"),
    expected_software_repository_version: int | None = Form(
        default=None, alias="expectedSoftwareRepositoryVersion"
    ),
    file: UploadFile | None = File(default=None),
    user_id: str = Depends(get_current_user_id),
    service: ApiInterfaceImportService = Depends(get_api_interface_import_service),
):
    return success_payload(
        await service.commit_import(
            user_id,
            software_repository_id,
            file=file,
            source_digest=source_digest,
            selected_keys=selected_keys,
            expected_items=expected_items,
            apply_base_path=apply_base_path,
            expected_software_repository_version=expected_software_repository_version,
        )
    )
