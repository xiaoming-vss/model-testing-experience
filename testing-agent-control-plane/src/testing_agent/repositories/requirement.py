from __future__ import annotations

from sqlalchemy import select

from testing_agent.models.requirement import Requirement
from testing_agent.repositories.base import ResourceRepository


class RequirementRepository(ResourceRepository):
    model = Requirement
    id_column = "requirement_id"

    async def get_active_by_sprint_and_name(self, sprint_id: str, name: str) -> Requirement | None:
        return await self.session.scalar(
            select(Requirement).where(
                Requirement.sprint_id == sprint_id,
                Requirement.name == name,
            )
        )

    async def get_by_sprint_and_name_unscoped(
        self, sprint_id: str, name: str
    ) -> Requirement | None:
        return await self.session.scalar(
            select(Requirement).where(
                Requirement.sprint_id == sprint_id,
                Requirement.name == name,
            )
        )

    async def list_active_by_sprint(self, sprint_id: str) -> list[Requirement]:
        return list(
            (
                await self.session.scalars(
                    select(Requirement)
                    .where(Requirement.sprint_id == sprint_id)
                    .order_by(Requirement.created_at.desc())
                )
            ).all()
        )

    def add(self, requirement: Requirement) -> None:
        self.session.add(requirement)

    async def refresh(self, requirement: Requirement) -> None:
        await self.session.refresh(requirement)
