from __future__ import annotations

from sqlalchemy import select

from testing_agent.models.sprint import Sprint
from testing_agent.repositories.base import ResourceRepository


class SprintRepository(ResourceRepository):
    model = Sprint
    id_column = "sprint_id"

    async def get_active_by_project_and_name(self, project_id: str, name: str) -> Sprint | None:
        return await self.session.scalar(
            select(Sprint).where(
                Sprint.project_id == project_id,
                Sprint.name == name,
            )
        )

    async def list_active_by_project(self, project_id: str) -> list[Sprint]:
        return list(
            (
                await self.session.scalars(
                    select(Sprint)
                    .where(Sprint.project_id == project_id)
                    .order_by(Sprint.created_at.desc())
                )
            ).all()
        )

    def add(self, sprint: Sprint) -> None:
        self.session.add(sprint)

    async def refresh(self, sprint: Sprint) -> None:
        await self.session.refresh(sprint)
