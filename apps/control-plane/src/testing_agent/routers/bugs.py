from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.bug import (
    comment_bug,
    create_bug,
    get_bug,
    list_bug_activities,
    list_project_bugs,
    transfer_bug,
    transition_bug,
    update_bug,
)
from testing_agent.schemas.bug import BugActivityResponse, BugResponse
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse

router = APIRouter()

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
