from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.function_test_case import (
    batch_delete_function_cases,
    create_function_case,
    delete_function_case,
    get_function_case,
    import_function_cases,
    import_function_cases_to_zentao,
    import_function_suites_to_zentao,
    list_function_cases,
    update_function_case,
)
from testing_agent.handlers.function_test_suite import (
    create_function_suite,
    delete_function_suite,
    get_function_suite,
    list_function_suites,
    update_function_suite,
)
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse
from testing_agent.schemas.function_test_case import (
    FunctionCaseImportResponse,
    FunctionCaseResponse,
    FunctionCasesBatchDeleteResponse,
    FunctionCaseZentaoImportResponse,
    FunctionSuitesZentaoImportResponse,
)
from testing_agent.schemas.function_test_suite import FunctionSuiteResponse

router = APIRouter()

router.post(
    "/requirements/{requirement_id}/function-test-suites",
    response_model=ApiResponse[FunctionSuiteResponse],
)(create_function_suite)
router.get(
    "/requirements/{requirement_id}/function-test-suites",
    response_model=ApiResponse[ListResponse[FunctionSuiteResponse]],
)(list_function_suites)
router.get(
    "/function-test-suites/{suite_id}",
    response_model=ApiResponse[FunctionSuiteResponse],
)(get_function_suite)
router.patch(
    "/function-test-suites/{suite_id}",
    response_model=ApiResponse[FunctionSuiteResponse],
)(update_function_suite)
router.delete(
    "/function-test-suites/{suite_id}",
    response_model=ApiResponse[EmptyData],
)(delete_function_suite)
router.post(
    "/function-test-suites/{suite_id}/cases",
    response_model=ApiResponse[FunctionCaseResponse],
)(create_function_case)
router.post(
    "/function-test-suites/{suite_id}/cases/import",
    response_model=ApiResponse[FunctionCaseImportResponse],
)(import_function_cases)
router.post(
    "/function-test-suites/{suite_id}/zentao/testcases/import",
    response_model=ApiResponse[FunctionCaseZentaoImportResponse],
)(import_function_cases_to_zentao)
router.post(
    "/requirements/{requirement_id}/zentao/testcases/import",
    response_model=ApiResponse[FunctionSuitesZentaoImportResponse],
    response_model_exclude_none=True,
)(import_function_suites_to_zentao)
router.get(
    "/function-test-suites/{suite_id}/cases",
    response_model=ApiResponse[ListResponse[FunctionCaseResponse]],
)(list_function_cases)
router.get(
    "/function-test-cases/{case_id}",
    response_model=ApiResponse[FunctionCaseResponse],
)(get_function_case)
router.patch(
    "/function-test-cases/{case_id}",
    response_model=ApiResponse[FunctionCaseResponse],
)(update_function_case)
router.delete(
    "/function-test-cases/{case_id}",
    response_model=ApiResponse[EmptyData],
)(delete_function_case)

router.post(
    "/function-test-suites/{suite_id}/cases/batch-delete",
    response_model=ApiResponse[FunctionCasesBatchDeleteResponse],
)(batch_delete_function_cases)
