from __future__ import annotations

from sqlalchemy import select

from testing_agent.models.perf_suite import PerfSuite
from testing_agent.repositories.base import ResourceRepository


class PerfSuiteRepository(ResourceRepository):
    model = PerfSuite
    id_column = "suite_id"

    async def get_suite(self, suite_id: str, *, for_update: bool = False) -> PerfSuite | None:
        query = select(PerfSuite).where(PerfSuite.suite_id == suite_id)
        if for_update:
            query = query.with_for_update()
        return await self.session.scalar(query.execution_options(populate_existing=True))

    async def get_by_project_and_name(self, project_id: str, name: str) -> PerfSuite | None:
        return await self.session.scalar(
            select(PerfSuite).where(PerfSuite.project_id == project_id, PerfSuite.name == name)
        )

    async def list_by_project(self, project_id: str) -> list[PerfSuite]:
        return list(
            (
                await self.session.scalars(
                    select(PerfSuite)
                    .where(PerfSuite.project_id == project_id)
                    .order_by(PerfSuite.updated_at.desc(), PerfSuite.id.desc())
                )
            ).all()
        )

    def add(self, suite: PerfSuite) -> None:
        self.session.add(suite)

    async def refresh(self, suite: PerfSuite) -> None:
        await self.session.refresh(suite)
