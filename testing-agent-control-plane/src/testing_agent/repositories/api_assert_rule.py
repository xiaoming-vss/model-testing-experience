from __future__ import annotations

from sqlalchemy import select

from testing_agent.models.api_assert_rule import ApiAssertRule
from testing_agent.repositories.base import ResourceRepository


class ApiAssertRuleRepository(ResourceRepository):
    model = ApiAssertRule
    id_column = "assert_rule_id"

    async def get_rule(self, assert_rule_id: str) -> ApiAssertRule | None:
        return await self.session.scalar(
            select(ApiAssertRule).where(
                ApiAssertRule.assert_rule_id == assert_rule_id,
            )
        )

    async def list_by_case(self, case_id: str) -> list[ApiAssertRule]:
        return list(
            (
                await self.session.scalars(
                    select(ApiAssertRule)
                    .where(
                        ApiAssertRule.case_id == case_id,
                    )
                    .order_by(ApiAssertRule.order_no)
                )
            ).all()
        )

    def add(self, rule: ApiAssertRule) -> None:
        self.session.add(rule)

    async def refresh(self, rule: ApiAssertRule) -> None:
        await self.session.refresh(rule)
