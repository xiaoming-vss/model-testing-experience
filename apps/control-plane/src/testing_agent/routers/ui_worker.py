from __future__ import annotations

from fastapi import APIRouter, Depends

from testing_agent.api.deps import verify_worker_token
from testing_agent.handlers.ui_worker import (
    claim_task,
    complete_suite_item,
    complete_task,
    get_snapshot,
    heartbeat,
    mark_started,
    mark_suite_item_started,
)
from testing_agent.schemas.workers import WorkerClaimPayload, WorkerSnapshotResponse

router = APIRouter(prefix="/ui-worker", dependencies=[Depends(verify_worker_token)])

router.post(
    "/tasks/claim",
    response_model=WorkerClaimPayload,
    response_model_exclude_none=True,
)(claim_task)
router.get("/tasks/{task_id}/snapshot", response_model=WorkerSnapshotResponse)(get_snapshot)
router.post("/tasks/{task_id}/started", status_code=204)(mark_started)
router.post("/tasks/{task_id}/heartbeat", status_code=204)(heartbeat)
router.post("/tasks/{task_id}/completed", status_code=204)(complete_task)
router.post("/tasks/{task_id}/suite-items/{item_id}/started", status_code=204)(
    mark_suite_item_started
)
router.post("/tasks/{task_id}/suite-items/{item_id}/completed", status_code=204)(
    complete_suite_item
)
