from __future__ import annotations

from fastapi import Depends, Query

from testing_agent.api.deps import get_bug_service, get_current_user_id
from testing_agent.core.errors import success_payload
from testing_agent.schemas.bug import (
    BugCommentRequest,
    BugCreateRequest,
    BugTransferRequest,
    BugTransitionRequest,
    BugUpdateRequest,
)
from testing_agent.services.bug import BugService


async def create_bug(
    project_id: str,
    body: BugCreateRequest,
    user_id: str = Depends(get_current_user_id),
    service: BugService = Depends(get_bug_service),
):
    return success_payload(await service.create(user_id, project_id, body))


async def list_project_bugs(
    project_id: str,
    status: str = Query(default=""),
    severity: str = Query(default=""),
    assignee_user_id: str = Query(default="", alias="assigneeUserId"),
    sprint_id: str = Query(default="", alias="sprintId"),
    sprint_filter: str = Query(default="found", alias="sprintFilter"),
    source_entry_id: str = Query(default="", alias="sourceEntryId"),
    keyword: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    service: BugService = Depends(get_bug_service),
):
    return success_payload(
        await service.list_project(
            user_id,
            project_id,
            statuses=[item.strip() for item in status.split(",") if item.strip()],
            severity=severity,
            assignee_user_id=assignee_user_id,
            sprint_id=sprint_id,
            sprint_filter=sprint_filter,
            source_entry_id=source_entry_id,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )
    )


async def get_bug(
    bug_id: str,
    user_id: str = Depends(get_current_user_id),
    service: BugService = Depends(get_bug_service),
):
    return success_payload(await service.get(user_id, bug_id))


async def update_bug(
    bug_id: str,
    body: BugUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    service: BugService = Depends(get_bug_service),
):
    return success_payload(
        await service.update(user_id, bug_id, body.model_dump(by_alias=False, exclude_none=True))
    )


async def transition_bug(
    bug_id: str,
    body: BugTransitionRequest,
    user_id: str = Depends(get_current_user_id),
    service: BugService = Depends(get_bug_service),
):
    return success_payload(await service.transition(user_id, bug_id, body))


async def transfer_bug(
    bug_id: str,
    body: BugTransferRequest,
    user_id: str = Depends(get_current_user_id),
    service: BugService = Depends(get_bug_service),
):
    return success_payload(await service.transfer(user_id, bug_id, body))


async def comment_bug(
    bug_id: str,
    body: BugCommentRequest,
    user_id: str = Depends(get_current_user_id),
    service: BugService = Depends(get_bug_service),
):
    return success_payload(await service.add_comment(user_id, bug_id, body.content))


async def list_bug_activities(
    bug_id: str,
    user_id: str = Depends(get_current_user_id),
    service: BugService = Depends(get_bug_service),
):
    return success_payload(await service.list_activities(user_id, bug_id))
