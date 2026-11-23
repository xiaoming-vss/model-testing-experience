from __future__ import annotations

from fastapi import Depends, Query

from testing_agent.api.deps import get_current_user_id, get_ui_test_case_service
from testing_agent.core.errors import success_payload
from testing_agent.schemas.case_lifecycle import CaseInvalidationRequest
from testing_agent.schemas.ui_test_case import UiCaseRequest, UiCaseUpdateRequest
from testing_agent.services.ui_test_case import UiTestCaseService


async def create_ui_case(
    suite_id: str,
    body: UiCaseRequest,
    user_id: str = Depends(get_current_user_id),
    service: UiTestCaseService = Depends(get_ui_test_case_service),
):
    return success_payload(await service.create(user_id, suite_id, body))


async def list_ui_cases(
    suite_id: str,
    invalidated: bool | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
    service: UiTestCaseService = Depends(get_ui_test_case_service),
):
    return success_payload(await service.list(user_id, suite_id, invalidated=invalidated))


async def batch_invalidate_ui_cases(
    project_id: str,
    body: CaseInvalidationRequest,
    user_id: str = Depends(get_current_user_id),
    service: UiTestCaseService = Depends(get_ui_test_case_service),
):
    return success_payload(
        await service.batch_set_invalidated(user_id, project_id, body.case_ids, body.invalidated)
    )


async def get_ui_case(
    case_id: str,
    user_id: str = Depends(get_current_user_id),
    service: UiTestCaseService = Depends(get_ui_test_case_service),
):
    return success_payload(await service.get(user_id, case_id))


async def update_ui_case(
    case_id: str,
    body: UiCaseUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    service: UiTestCaseService = Depends(get_ui_test_case_service),
):
    return success_payload(
        await service.update(user_id, case_id, body.model_dump(by_alias=True, exclude_unset=True))
    )


async def delete_ui_case(
    case_id: str,
    user_id: str = Depends(get_current_user_id),
    service: UiTestCaseService = Depends(get_ui_test_case_service),
):
    return success_payload(await service.delete(user_id, case_id))
