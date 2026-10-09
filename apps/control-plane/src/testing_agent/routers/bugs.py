from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.bug import (
    comment_bug,
    create_bug,
    get_bug,
    get_bug_options,
    list_bug_activities,
    list_project_bugs,
    transfer_bug,
    transition_bug,
    update_bug,
)
from testing_agent.handlers.bug_zentao_pull import get_bug_zentao_remote, pull_bug_zentao
from testing_agent.handlers.bug_zentao_push import (
    get_bug_zentao_push,
    get_bug_zentao_push_options,
    reconcile_bug_attachment,
    reconcile_bug_zentao_push,
)
from testing_agent.handlers.integration_bug import get_job, submit_fields, submit_sync
from testing_agent.schemas.bug import BugActivityResponse, BugOptionsResponse, BugResponse
from testing_agent.schemas.bug_zentao_pull import (
    ZentaoPullResponse,
    ZentaoRemotePreviewResponse,
)
from testing_agent.schemas.bug_zentao_push import (
    BugZentaoPushOptionsResponse,
    BugZentaoPushResponse,
)
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse
from testing_agent.schemas.integration_bug import IntegrationJobSummary

router = APIRouter()

router.post(
    "/bugs/{bug_id}/zentao-sync-jobs",
    status_code=202,
    response_model=ApiResponse[IntegrationJobSummary],
)(submit_sync)
router.post(
    "/bugs/{bug_id}/zentao-field-update-jobs",
    status_code=202,
    response_model=ApiResponse[IntegrationJobSummary],
)(submit_fields)
router.get(
    "/bugs/{bug_id}/zentao-jobs/{job_id}", response_model=ApiResponse[IntegrationJobSummary]
)(get_job)

router.get(
    "/bugs/{bug_id}/zentao-push/options",
    response_model=ApiResponse[BugZentaoPushOptionsResponse],
)(get_bug_zentao_push_options)

router.get("/bugs/{bug_id}/zentao-push", response_model=ApiResponse[BugZentaoPushResponse])(
    get_bug_zentao_push
)
router.post(
    "/bugs/{bug_id}/zentao-push/reconcile", response_model=ApiResponse[BugZentaoPushResponse]
)(reconcile_bug_zentao_push)

router.post(
    "/bugs/{bug_id}/zentao-push/attachments/{file_id}/reconcile",
    response_model=ApiResponse[BugZentaoPushResponse],
)(reconcile_bug_attachment)

router.get(
    "/bugs/{bug_id}/zentao-remote",
    response_model=ApiResponse[ZentaoRemotePreviewResponse],
)(get_bug_zentao_remote)
router.post(
    "/bugs/{bug_id}/zentao-pull",
    response_model=ApiResponse[ZentaoPullResponse],
)(pull_bug_zentao)

router.get(
    "/projects/{project_id}/bugs/options",
    response_model=ApiResponse[BugOptionsResponse],
)(get_bug_options)

router.post(
    "/projects/{project_id}/bugs",
    response_model=ApiResponse[BugResponse],
)(create_bug)
router.get(
    "/projects/{project_id}/bugs",
    response_model=ApiResponse[ListResponse[BugResponse]],
)(list_project_bugs)
router.get(
    "/bugs/{bug_id}",
    response_model=ApiResponse[BugResponse],
)(get_bug)
router.patch(
    "/bugs/{bug_id}",
    response_model=ApiResponse[BugResponse],
)(update_bug)
router.post(
    "/bugs/{bug_id}/transition",
    response_model=ApiResponse[BugResponse],
)(transition_bug)
router.post(
    "/bugs/{bug_id}/transfer",
    response_model=ApiResponse[BugResponse],
)(transfer_bug)
router.post(
    "/bugs/{bug_id}/comments",
    response_model=ApiResponse[EmptyData],
)(comment_bug)
router.get(
    "/bugs/{bug_id}/activities",
    response_model=ApiResponse[ListResponse[BugActivityResponse]],
)(list_bug_activities)
