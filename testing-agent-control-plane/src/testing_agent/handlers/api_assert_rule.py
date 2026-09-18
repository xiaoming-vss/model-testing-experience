from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import get_api_assert_rule_service, get_current_user_id
from testing_agent.core.errors import success_payload
from testing_agent.schemas.api_assert_rule import ApiAssertRuleRequest, ApiAssertRuleUpdateRequest
from testing_agent.services.api_assert_rule import ApiAssertRuleService


async def create_api_assert_rule(
    case_id: str,
    body: ApiAssertRuleRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiAssertRuleService = Depends(get_api_assert_rule_service),
):
    return success_payload(await service.create(user_id, case_id, body))


async def list_api_assert_rules(
    case_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiAssertRuleService = Depends(get_api_assert_rule_service),
):
    return success_payload(await service.list(user_id, case_id))


async def get_api_assert_rule(
    assert_rule_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiAssertRuleService = Depends(get_api_assert_rule_service),
):
    return success_payload(await service.get(user_id, assert_rule_id))


async def update_api_assert_rule(
    assert_rule_id: str,
    body: ApiAssertRuleUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiAssertRuleService = Depends(get_api_assert_rule_service),
):
    return success_payload(
        await service.update(
            user_id,
            assert_rule_id,
            body.model_dump(by_alias=True, exclude_none=True),
        )
    )


async def delete_api_assert_rule(
    assert_rule_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiAssertRuleService = Depends(get_api_assert_rule_service),
):
    return success_payload(await service.delete(user_id, assert_rule_id))
