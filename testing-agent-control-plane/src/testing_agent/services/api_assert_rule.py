from __future__ import annotations

from typing import Any

from testing_agent.core.errors import ErrNotFound
from testing_agent.core.sid import new_id
from testing_agent.models.api_assert_rule import ApiAssertRule
from testing_agent.repositories.api_assert_rule import ApiAssertRuleRepository
from testing_agent.schemas.api_assert_rule import ApiAssertRuleRequest, ApiAssertRuleResponse
from testing_agent.services.api_case import ApiCaseService
from testing_agent.services.common import apply_patch, dump, list_payload
from testing_agent.services.project_access import ProjectAction


class ApiAssertRuleService:
    def __init__(self, repository: ApiAssertRuleRepository, api_cases: ApiCaseService):
        self.repository = repository
        self.api_cases = api_cases

    async def get_accessible_entity(
        self, user_id: str, assert_rule_id: str, *, action: ProjectAction = "read"
    ) -> ApiAssertRule:
        rule = await self.repository.get_rule(assert_rule_id)
        if rule is None:
            raise ErrNotFound
        await self.api_cases.get_accessible_context(user_id, rule.case_id, action=action)
        return rule

    async def create(self, user_id: str, case_id: str, body: ApiAssertRuleRequest) -> dict:
        await self.api_cases.get_accessible_context(user_id, case_id, action="write")
        rule = ApiAssertRule(assert_rule_id=new_id(), case_id=case_id, **body.model_dump())
        self.repository.add(rule)
        await self.repository.commit()
        await self.repository.refresh(rule)
        return dump(ApiAssertRuleResponse, rule)

    async def list(self, user_id: str, case_id: str) -> dict[str, Any]:
        await self.api_cases.get_accessible_context(user_id, case_id, action="read")
        rows = await self.repository.list_by_case(case_id)
        return list_payload([dump(ApiAssertRuleResponse, row) for row in rows])

    async def get(self, user_id: str, assert_rule_id: str) -> dict:
        return dump(
            ApiAssertRuleResponse,
            await self.get_accessible_entity(user_id, assert_rule_id, action="read"),
        )

    async def update(self, user_id: str, assert_rule_id: str, body: dict[str, Any]) -> dict:
        rule = await self.get_accessible_entity(user_id, assert_rule_id, action="write")
        apply_patch(
            rule,
            body,
            {
                "name",
                "enabled",
                "order_no",
                "assert_source",
                "target_expr",
                "comparator",
                "expected_value",
            },
        )
        await self.repository.commit()
        await self.repository.refresh(rule)
        return dump(ApiAssertRuleResponse, rule)

    async def delete(self, user_id: str, assert_rule_id: str) -> dict:
        rule = await self.get_accessible_entity(user_id, assert_rule_id, action="write")
        await self.repository.hard_delete(rule)
        await self.repository.commit()
        return {}
