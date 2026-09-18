from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from testing_agent.api.deps import verify_worker_token
from testing_agent.handlers.ai_worker import (
    claim_task,
    complete_task,
    get_snapshot,
    gitlab_credentials,
    heartbeat,
    list_project_skills,
    llm_credentials,
    mark_started,
    report_progress,
    requirement_document,
    source_archive,
)
from testing_agent.schemas.workers import (
    WorkerClaimPayload,
    WorkerGitlabCredentialsResponse,
    WorkerLlmCredentialsResponse,
    WorkerProjectSkillsResponse,
    WorkerSnapshotResponse,
)

router = APIRouter(prefix="/ai-worker", dependencies=[Depends(verify_worker_token)])

router.post(
    "/tasks/claim",
    response_model=WorkerClaimPayload,
    response_model_exclude_none=True,
)(claim_task)
router.get("/tasks/{task_id}/snapshot", response_model=WorkerSnapshotResponse)(get_snapshot)
router.post("/tasks/{task_id}/started", status_code=204)(mark_started)
router.post("/tasks/{task_id}/heartbeat", status_code=204)(heartbeat)
router.post("/tasks/{task_id}/completed", status_code=204)(complete_task)
router.get("/projects/{project_id}/skills", response_model=WorkerProjectSkillsResponse)(
    list_project_skills
)
router.get(
    "/tasks/{task_id}/llm-credentials",
    response_model=WorkerLlmCredentialsResponse,
)(llm_credentials)
router.get(
    "/tasks/{task_id}/gitlab-credentials",
    response_model=WorkerGitlabCredentialsResponse,
)(gitlab_credentials)
router.get(
    "/tasks/{task_id}/requirement-document",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)(requirement_document)
router.get(
    "/tasks/{task_id}/source-archive",
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}}},
)(source_archive)
router.patch("/tasks/{task_id}/progress", status_code=204)(report_progress)
