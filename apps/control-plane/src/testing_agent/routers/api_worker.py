from __future__ import annotations

from fastapi import APIRouter, Depends

from testing_agent.api.deps import verify_worker_token
from testing_agent.handlers.api_worker import (
    claim_task,
    complete_collection_item,
    complete_task,
    get_snapshot,
    heartbeat,
    mark_collection_item_started,
    mark_started,
)
from testing_agent.schemas.common import ApiResponse
from testing_agent.schemas.workers import (
    WorkerClaimPayload,
    WorkerItemAckResponse,
    WorkerSnapshotResponse,
    WorkerTaskAckResponse,
)

router = APIRouter(prefix="/api-worker", dependencies=[Depends(verify_worker_token)])

router.post("/tasks/claim", response_model=ApiResponse[WorkerClaimPayload])(claim_task)
router.get(
    "/tasks/{task_id}/snapshot",
    response_model=ApiResponse[WorkerSnapshotResponse],
)(get_snapshot)
router.post(
    "/tasks/{task_id}/started",
    response_model=ApiResponse[WorkerTaskAckResponse],
)(mark_started)
router.post(
    "/tasks/{task_id}/heartbeat",
    response_model=ApiResponse[WorkerTaskAckResponse],
)(heartbeat)
router.post(
    "/tasks/{task_id}/completed",
    response_model=ApiResponse[WorkerTaskAckResponse],
)(complete_task)
router.post(
    "/tasks/{task_id}/collection-items/{item_id}/started",
    response_model=ApiResponse[WorkerItemAckResponse],
)(mark_collection_item_started)
router.post(
    "/tasks/{task_id}/collection-items/{item_id}/completed",
    response_model=ApiResponse[WorkerItemAckResponse],
)(complete_collection_item)
