from __future__ import annotations

from typing import Any

from fastapi import Body, Depends, File, Query, UploadFile

from testing_agent.api.deps import get_current_user_id, get_function_test_case_service
from testing_agent.core.errors import success_payload
from testing_agent.domain.function_case_query import FunctionCaseQuery
from testing_agent.schemas.function_test_case import (
    FunctionCaseRequest,
    FunctionCasesBatchDeleteRequest,
    FunctionCaseUpdateRequest,
    ImportFunctionCasesToZentaoRequest,
    ImportFunctionSuitesToZentaoRequest,
)
from testing_agent.services.function_test_case import FunctionTestCaseService


async def create_function_case(
    suite_id: str,
    body: FunctionCaseRequest,
    user_id: str = Depends(get_current_user_id),
    service: FunctionTestCaseService = Depends(get_function_test_case_service),
):
    return success_payload(await service.create(user_id, suite_id, body))


async def import_function_cases(
    suite_id: str,
    payload: Any = Body(default=None),
    file: UploadFile | None = File(default=None),
    user_id: str = Depends(get_current_user_id),
    service: FunctionTestCaseService = Depends(get_function_test_case_service),
):
    return success_payload(await service.import_cases(user_id, suite_id, payload, file))


async def import_function_cases_to_zentao(
    suite_id: str,
    payload: ImportFunctionCasesToZentaoRequest = Body(),
    user_id: str = Depends(get_current_user_id),
    service: FunctionTestCaseService = Depends(get_function_test_case_service),
):
    return success_payload(await service.import_to_zentao(user_id, suite_id, payload))


async def import_function_suites_to_zentao(
    requirement_id: str,
    payload: ImportFunctionSuitesToZentaoRequest = Body(),
    user_id: str = Depends(get_current_user_id),
    service: FunctionTestCaseService = Depends(get_function_test_case_service),
):
    return success_payload(
        await service.import_requirement_to_zentao(user_id, requirement_id, payload)
    )


async def list_function_cases(
    suite_id: str,
    user_id: str = Depends(get_current_user_id),
    service: FunctionTestCaseService = Depends(get_function_test_case_service),
):
    return success_payload(await service.list(user_id, suite_id))


async def list_project_function_cases(
    project_id: str,
    sprint_id: str = Query(default="", alias="sprintId"),
    requirement_id: str = Query(default="", alias="requirementId"),
    suite_id: str = Query(default="", alias="suiteId"),
    module: str = Query(default=""),
    priority: str = Query(default=""),
    case_type: str = Query(default="", alias="caseType"),
    keyword: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    service: FunctionTestCaseService = Depends(get_function_test_case_service),
):
    return success_payload(
        await service.list_project_cases(
            user_id,
            FunctionCaseQuery.for_page(
                project_id,
                page=page,
                page_size=page_size,
                sprint_id=sprint_id,
                requirement_id=requirement_id,
                suite_id=suite_id,
                module=module,
                priority=priority,
                case_type=case_type,
                keyword=keyword,
            ),
        )
    )


async def get_function_case(
    case_id: str,
    user_id: str = Depends(get_current_user_id),
    service: FunctionTestCaseService = Depends(get_function_test_case_service),
):
    return success_payload(await service.get(user_id, case_id))


async def update_function_case(
    case_id: str,
    body: FunctionCaseUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    service: FunctionTestCaseService = Depends(get_function_test_case_service),
):
    return success_payload(
        await service.update(user_id, case_id, body.model_dump(by_alias=True, exclude_none=True))
    )


async def delete_function_case(
    case_id: str,
    user_id: str = Depends(get_current_user_id),
    service: FunctionTestCaseService = Depends(get_function_test_case_service),
):
    return success_payload(await service.delete(user_id, case_id))


async def batch_delete_function_cases(
    suite_id: str,
    body: FunctionCasesBatchDeleteRequest,
    user_id: str = Depends(get_current_user_id),
    service: FunctionTestCaseService = Depends(get_function_test_case_service),
):
    return success_payload(await service.batch_delete(user_id, suite_id, body.case_ids))
