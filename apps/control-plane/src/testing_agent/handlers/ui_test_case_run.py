from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import get_current_user_id, get_ui_test_case_run_service
from testing_agent.core.errors import success_payload
from testing_agent.schemas.ui_run import DebugRunUiCaseRequest, RunUiSuiteRequest
from testing_agent.services.ui_test_case_run import UiTestCaseRunService


async def debug_run_ui_case(
    case_id: str,
    body: DebugRunUiCaseRequest,
    user_id: str = Depends(get_current_user_id),
    service: UiTestCaseRunService = Depends(get_ui_test_case_run_service),
):
    return success_payload(await service.debug_run_case(user_id, case_id, body))


async def get_ui_case_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: UiTestCaseRunService = Depends(get_ui_test_case_run_service),
):
    return success_payload(await service.get_case_run(user_id, run_id))


async def run_ui_suite(
    suite_id: str,
    body: RunUiSuiteRequest,
    user_id: str = Depends(get_current_user_id),
    service: UiTestCaseRunService = Depends(get_ui_test_case_run_service),
):
    return success_payload(await service.run_suite(user_id, suite_id, body))


async def list_ui_suite_runs(
    suite_id: str,
    user_id: str = Depends(get_current_user_id),
    service: UiTestCaseRunService = Depends(get_ui_test_case_run_service),
):
    return success_payload(await service.list_suite_runs(user_id, suite_id))


async def get_ui_suite_run(
    suite_run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: UiTestCaseRunService = Depends(get_ui_test_case_run_service),
):
    return success_payload(await service.get_suite_run(user_id, suite_run_id))


async def get_ui_suite_run_report(
    suite_run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: UiTestCaseRunService = Depends(get_ui_test_case_run_service),
):
    return success_payload(await service.suite_report(user_id, suite_run_id))
