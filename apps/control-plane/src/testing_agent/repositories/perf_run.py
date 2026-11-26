from __future__ import annotations

from sqlalchemy import func, select

from testing_agent.models.perf_run import PerfRun
from testing_agent.repositories.base import ResourceRepository


class PerfRunRepository(ResourceRepository):
    model = PerfRun
    id_column = "run_id"

    async def get_run(self, run_id: str, *, for_update: bool = False) -> PerfRun | None:
        query = select(PerfRun).where(PerfRun.run_id == run_id)
        if for_update:
            query = query.with_for_update()
        return await self.session.scalar(query.execution_options(populate_existing=True))

    async def list_by_project(
        self,
        project_id: str,
        *,
        case_id: str = "",
        status: str = "",
        trigger_type: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[PerfRun], int]:
        conditions = [PerfRun.project_id == project_id]
        if case_id:
            conditions.append(PerfRun.case_id == case_id)
        if status:
            conditions.append(PerfRun.status == status)
        if trigger_type:
            conditions.append(PerfRun.trigger_type == trigger_type)
        total = await self.session.scalar(
            select(func.count()).select_from(PerfRun).where(*conditions)
        )
        rows = list(
            (
                await self.session.scalars(
                    select(PerfRun)
                    .where(*conditions)
                    .order_by(PerfRun.created_at.desc(), PerfRun.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        return rows, int(total or 0)

    async def list_by_ids(self, run_ids: list[str]) -> dict[str, PerfRun]:
        if not run_ids:
            return {}
        rows = list(
            (await self.session.scalars(select(PerfRun).where(PerfRun.run_id.in_(run_ids)))).all()
        )
        return {row.run_id: row for row in rows}

    def add(self, run: PerfRun) -> None:
        self.session.add(run)

    async def refresh(self, run: PerfRun) -> None:
        await self.session.refresh(run)
