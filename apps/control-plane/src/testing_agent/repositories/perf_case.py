from __future__ import annotations

from sqlalchemy import func, select

from testing_agent.models.perf_case import PerfCase
from testing_agent.models.project import Project
from testing_agent.repositories.base import ResourceRepository


class PerfCaseRepository(ResourceRepository):
    model = PerfCase
    id_column = "case_id"

    async def get_project(self, project_id: str) -> Project | None:
        return await self.session.scalar(select(Project).where(Project.project_id == project_id))

    async def get_case(self, case_id: str, *, for_update: bool = False) -> PerfCase | None:
        query = select(PerfCase).where(PerfCase.case_id == case_id)
        if for_update:
            query = query.with_for_update()
        return await self.session.scalar(query.execution_options(populate_existing=True))

    async def get_by_project_and_name(self, project_id: str, name: str) -> PerfCase | None:
        return await self.session.scalar(
            select(PerfCase).where(PerfCase.project_id == project_id, PerfCase.name == name)
        )

    async def list_by_project(self, project_id: str) -> list[PerfCase]:
        return list(
            (
                await self.session.scalars(
                    select(PerfCase)
                    .where(PerfCase.project_id == project_id)
                    .order_by(PerfCase.created_at.desc(), PerfCase.id.desc())
                )
            ).all()
        )

    async def list_by_suite(self, suite_id: str) -> list[PerfCase]:
        return list(
            (
                await self.session.scalars(
                    select(PerfCase)
                    .where(PerfCase.suite_id == suite_id)
                    .order_by(PerfCase.order_no.asc(), PerfCase.created_at.asc(), PerfCase.id.asc())
                )
            ).all()
        )

    async def next_order_no(self, suite_id: str) -> int:
        current = await self.session.scalar(
            select(func.max(PerfCase.order_no)).where(PerfCase.suite_id == suite_id)
        )
        return int(current or 0) + 1

    def add(self, case: PerfCase) -> None:
        self.session.add(case)

    async def refresh(self, case: PerfCase) -> None:
        await self.session.refresh(case)
