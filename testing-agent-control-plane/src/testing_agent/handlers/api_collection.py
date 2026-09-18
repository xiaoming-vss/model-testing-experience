from __future__ import annotations

from typing import Any

from fastapi import Body, Depends, File, UploadFile

from testing_agent.api.deps import get_api_collection_service, get_current_user_id
from testing_agent.core.errors import success_payload
from testing_agent.schemas.api_collection import ApiCollectionRequest, ApiCollectionUpdateRequest
from testing_agent.services.api_collection import ApiCollectionService


async def create_api_collection(
    requirement_id: str,
    body: ApiCollectionRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiCollectionService = Depends(get_api_collection_service),
):
    return success_payload(await service.create(user_id, requirement_id, body))


async def list_api_collections(
    requirement_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiCollectionService = Depends(get_api_collection_service),
):
    return success_payload(await service.list(user_id, requirement_id))


async def get_api_collection(
    collection_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiCollectionService = Depends(get_api_collection_service),
):
    return success_payload(await service.get(user_id, collection_id))


async def update_api_collection(
    collection_id: str,
    body: ApiCollectionUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiCollectionService = Depends(get_api_collection_service),
):
    return success_payload(
        await service.update(
            user_id,
            collection_id,
            body.model_dump(by_alias=True, exclude_none=True),
        )
    )


async def delete_api_collection(
    collection_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiCollectionService = Depends(get_api_collection_service),
):
    return success_payload(await service.delete(user_id, collection_id))


async def import_api_cases(
    collection_id: str,
    payload: Any = Body(default=None),
    file: UploadFile | None = File(default=None),
    user_id: str = Depends(get_current_user_id),
    service: ApiCollectionService = Depends(get_api_collection_service),
):
    return success_payload(await service.import_cases(user_id, collection_id, payload, file))
