from fastapi import APIRouter, Depends

from testing_agent.api.deps import verify_integration_worker_token
from testing_agent.handlers import integration_worker as handlers

router = APIRouter(
    prefix="/integration-worker",
    dependencies=[
        Depends(verify_integration_worker_token),
        Depends(handlers.no_store),
    ],
)
router.post("/jobs/claim")(handlers.claim)
router.get("/jobs/{job_id}/input")(handlers.input)
router.post("/jobs/{job_id}/access")(handlers.access)
router.post("/jobs/{job_id}/heartbeat")(handlers.heartbeat)
router.post("/jobs/{job_id}/steps/{step_key}/prepare")(handlers.prepare)
router.post("/jobs/{job_id}/steps/{step_key}/result")(handlers.result)
router.post("/jobs/{job_id}/steps/{step_key}/evidence")(handlers.evidence)
router.post("/jobs/{job_id}/steps/{step_key}/preflight-failure")(handlers.failure)
router.post("/jobs/{job_id}/completed")(handlers.completed)
