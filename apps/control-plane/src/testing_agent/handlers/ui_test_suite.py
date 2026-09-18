from __future__ import annotations

from typing import Any

from fastapi import Body, Depends, File, UploadFile

from testing_agent.api.deps import (
    get_current_user_id,
    get_ui_test_case_service,
    get_ui_test_suite_service,
)
from testing_agent.core.errors import success_payload
from testing_agent.schemas.ui_test_suite import UiSuiteRequest, UiSuiteUpdateRequest
from testing_agent.services.ui_test_case import UiTestCaseService
from testing_agent.services.ui_test_suite import UiTestSuiteService


async def create_ui_suite(
    requirement_id: str,
    body: UiSuiteRequest,
    user_id: str = Depends(get_current_user_id),
    service: UiTestSuiteService = Depends(get_ui_test_suite_service),
):
    return success_payload(await service.create(user_id, requirement_id, body))


async def list_ui_suites(
    requirement_id: str,
    user_id: str = Depends(get_current_user_id),
    service: UiTestSuiteService = Depends(get_ui_test_suite_service),
):
    return success_payload(await service.list(user_id, requirement_id))


async def get_ui_suite(
    suite_id: str,
    user_id: str = Depends(get_current_user_id),
    service: UiTestSuiteService = Depends(get_ui_test_suite_service),
):
    return success_payload(await service.get(user_id, suite_id))


async def update_ui_suite(
    suite_id: str,
    body: UiSuiteUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    service: UiTestSuiteService = Depends(get_ui_test_suite_service),
):
    return success_payload(
        await service.update(user_id, suite_id, body.model_dump(by_alias=False, exclude_none=True))
    )


async def delete_ui_suite(
    suite_id: str,
    user_id: str = Depends(get_current_user_id),
    service: UiTestSuiteService = Depends(get_ui_test_suite_service),
):
    return success_payload(await service.delete(user_id, suite_id))


async def import_ui_cases(
    suite_id: str,
    payload: Any = Body(default=None),
    file: UploadFile | None = File(default=None),
    user_id: str = Depends(get_current_user_id),
    service: UiTestCaseService = Depends(get_ui_test_case_service),
):
    return success_payload(await service.import_cases(user_id, suite_id, payload, file))
