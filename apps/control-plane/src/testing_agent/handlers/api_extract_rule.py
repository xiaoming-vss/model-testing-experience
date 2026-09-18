from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import get_api_extract_rule_service, get_current_user_id
from testing_agent.core.errors import success_payload
from testing_agent.schemas.api_extract_rule import (
    ApiExtractRuleRequest,
    ApiExtractRuleUpdateRequest,
)
from testing_agent.services.api_extract_rule import ApiExtractRuleService


async def create_api_extract_rule(
    case_id: str,
    body: ApiExtractRuleRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiExtractRuleService = Depends(get_api_extract_rule_service),
):
    return success_payload(await service.create(user_id, case_id, body))


async def list_api_extract_rules(
    case_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiExtractRuleService = Depends(get_api_extract_rule_service),
):
    return success_payload(await service.list(user_id, case_id))


async def get_api_extract_rule(
    extract_rule_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiExtractRuleService = Depends(get_api_extract_rule_service),
):
    return success_payload(await service.get(user_id, extract_rule_id))


async def update_api_extract_rule(
    extract_rule_id: str,
    body: ApiExtractRuleUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiExtractRuleService = Depends(get_api_extract_rule_service),
):
    return success_payload(
        await service.update(
            user_id,
            extract_rule_id,
            body.model_dump(by_alias=True, exclude_none=True),
        )
    )


async def delete_api_extract_rule(
    extract_rule_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiExtractRuleService = Depends(get_api_extract_rule_service),
):
    return success_payload(await service.delete(user_id, extract_rule_id))
