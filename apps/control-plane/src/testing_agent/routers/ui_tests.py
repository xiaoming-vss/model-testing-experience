from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.ui_test_case import (
    create_ui_case,
    delete_ui_case,
    get_ui_case,
    list_ui_cases,
    update_ui_case,
)
from testing_agent.handlers.ui_test_suite import (
    create_ui_suite,
    delete_ui_suite,
    get_ui_suite,
    import_ui_cases,
    list_ui_suites,
    update_ui_suite,
)
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse
from testing_agent.schemas.ui_test_case import UiCaseImportResponse, UiCaseResponse
from testing_agent.schemas.ui_test_suite import UiSuiteResponse

router = APIRouter()

router.post(
    "/requirements/{requirement_id}/ui-test-suites",
    response_model=ApiResponse[UiSuiteResponse],
)(create_ui_suite)
router.get(
    "/requirements/{requirement_id}/ui-test-suites",
    response_model=ApiResponse[ListResponse[UiSuiteResponse]],
)(list_ui_suites)
router.get("/ui-test-suites/{suite_id}", response_model=ApiResponse[UiSuiteResponse])(get_ui_suite)
router.patch("/ui-test-suites/{suite_id}", response_model=ApiResponse[UiSuiteResponse])(
    update_ui_suite
)
router.delete("/ui-test-suites/{suite_id}", response_model=ApiResponse[EmptyData])(delete_ui_suite)
router.post("/ui-test-suites/{suite_id}/cases", response_model=ApiResponse[UiCaseResponse])(
    create_ui_case
)
router.post(
    "/ui-test-suites/{suite_id}/import",
    response_model=ApiResponse[UiCaseImportResponse],
)(import_ui_cases)
router.get(
    "/ui-test-suites/{suite_id}/cases",
    response_model=ApiResponse[ListResponse[UiCaseResponse]],
)(list_ui_cases)
router.get("/ui-test-cases/{case_id}", response_model=ApiResponse[UiCaseResponse])(get_ui_case)
router.patch("/ui-test-cases/{case_id}", response_model=ApiResponse[UiCaseResponse])(update_ui_case)
router.delete("/ui-test-cases/{case_id}", response_model=ApiResponse[EmptyData])(delete_ui_case)
