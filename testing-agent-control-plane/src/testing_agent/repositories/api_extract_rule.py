from __future__ import annotations

from sqlalchemy import select

from testing_agent.models.api_extract_rule import ApiExtractRule
from testing_agent.repositories.base import ResourceRepository


class ApiExtractRuleRepository(ResourceRepository):
    model = ApiExtractRule
    id_column = "extract_rule_id"

    async def get_rule(self, extract_rule_id: str) -> ApiExtractRule | None:
        return await self.session.scalar(
            select(ApiExtractRule).where(
                ApiExtractRule.extract_rule_id == extract_rule_id,
            )
        )

    async def list_by_case(self, case_id: str) -> list[ApiExtractRule]:
        return list(
            (
                await self.session.scalars(
                    select(ApiExtractRule)
                    .where(
                        ApiExtractRule.case_id == case_id,
                    )
                    .order_by(ApiExtractRule.order_no)
                )
            ).all()
        )

    def add(self, rule: ApiExtractRule) -> None:
        self.session.add(rule)

    async def refresh(self, rule: ApiExtractRule) -> None:
        await self.session.refresh(rule)
