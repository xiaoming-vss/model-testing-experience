from __future__ import annotations

from fastapi import APIRouter, Depends

from testing_agent.api.deps import verify_perf_worker_token
from testing_agent.handlers import perf_worker as handlers

router = APIRouter(
    prefix="/perf-worker",
    dependencies=[
        Depends(verify_perf_worker_token),
        Depends(handlers.no_store),
    ],
)
router.post("/tasks/claim")(handlers.claim)
router.get("/tasks/{task_id}/snapshot")(handlers.snapshot)
router.post("/tasks/{task_id}/started")(handlers.started)
router.post("/tasks/{task_id}/heartbeat")(handlers.heartbeat)
router.get("/tasks/{task_id}/control")(handlers.control)
router.post("/tasks/{task_id}/completed")(handlers.completed)
router.get("/tasks/{task_id}/data-files/{file_id}")(handlers.data_file)
