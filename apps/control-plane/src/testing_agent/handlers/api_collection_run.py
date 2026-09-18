from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import (
    get_api_collection_run_service,
    get_current_user_id,
)
from testing_agent.core.errors import success_payload
from testing_agent.schemas.api_run import RunApiCollectionRequest
from testing_agent.services.api_collection_run import ApiCollectionRunService


async def run_api_collection(
    collection_id: str,
    body: RunApiCollectionRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiCollectionRunService = Depends(get_api_collection_run_service),
):
    return success_payload(await service.run(user_id, collection_id, body))


async def list_api_collection_runs(
    collection_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiCollectionRunService = Depends(get_api_collection_run_service),
):
    return success_payload(await service.list(user_id, collection_id))


async def get_api_collection_run(
    collection_run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiCollectionRunService = Depends(get_api_collection_run_service),
):
    return success_payload(await service.get(user_id, collection_run_id))


async def get_api_collection_run_report(
    collection_run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiCollectionRunService = Depends(get_api_collection_run_service),
):
    return success_payload(await service.report(user_id, collection_run_id))
