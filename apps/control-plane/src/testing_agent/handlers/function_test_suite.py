from __future__ import annotations

from fastapi import Depends, Query

from testing_agent.api.deps import get_current_user_id, get_function_test_suite_service
from testing_agent.core.errors import success_payload
from testing_agent.schemas.function_test_suite import (
    FunctionSuiteRequest,
    FunctionSuiteUpdateRequest,
)
from testing_agent.services.function_test_suite import FunctionTestSuiteService


async def create_function_suite(
    requirement_id: str,
    body: FunctionSuiteRequest,
    user_id: str = Depends(get_current_user_id),
    service: FunctionTestSuiteService = Depends(get_function_test_suite_service),
):
    return success_payload(await service.create(user_id, requirement_id, body))


async def list_function_suites(
    requirement_id: str,
    user_id: str = Depends(get_current_user_id),
    service: FunctionTestSuiteService = Depends(get_function_test_suite_service),
):
    return success_payload(await service.list(user_id, requirement_id))


async def list_project_function_suites(
    project_id: str,
    sprint_id: str = Query(default="", alias="sprintId"),
    requirement_id: str = Query(default="", alias="requirementId"),
    user_id: str = Depends(get_current_user_id),
    service: FunctionTestSuiteService = Depends(get_function_test_suite_service),
):
    return success_payload(
        await service.list_project(
            user_id, project_id, sprint_id=sprint_id, requirement_id=requirement_id
        )
    )


async def get_function_suite(
    suite_id: str,
    user_id: str = Depends(get_current_user_id),
    service: FunctionTestSuiteService = Depends(get_function_test_suite_service),
):
    return success_payload(await service.get(user_id, suite_id))


async def get_function_suite_requirement_case_view(
    suite_id: str,
    user_id: str = Depends(get_current_user_id),
    service: FunctionTestSuiteService = Depends(get_function_test_suite_service),
):
    return success_payload(await service.requirement_case_view(user_id, suite_id))


async def update_function_suite(
    suite_id: str,
    body: FunctionSuiteUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    service: FunctionTestSuiteService = Depends(get_function_test_suite_service),
):
    return success_payload(
        await service.update(user_id, suite_id, body.model_dump(by_alias=True, exclude_none=True))
    )


async def delete_function_suite(
    suite_id: str,
    user_id: str = Depends(get_current_user_id),
    service: FunctionTestSuiteService = Depends(get_function_test_suite_service),
):
    return success_payload(await service.delete(user_id, suite_id))
