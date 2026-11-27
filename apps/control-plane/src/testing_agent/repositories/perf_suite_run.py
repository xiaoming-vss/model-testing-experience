from __future__ import annotations

from sqlalchemy import func, select

from testing_agent.models.perf_suite_run import PerfSuiteRun, PerfSuiteRunItem
from testing_agent.repositories.base import ResourceRepository
from testing_agent.repositories.latest import latest_per_resource


class PerfSuiteRunRepository(ResourceRepository):
    model = PerfSuiteRun
    id_column = "suite_run_id"

    async def get_run(self, suite_run_id: str, *, for_update: bool = False) -> PerfSuiteRun | None:
        query = select(PerfSuiteRun).where(PerfSuiteRun.suite_run_id == suite_run_id)
        if for_update:
            query = query.with_for_update()
        return await self.session.scalar(query.execution_options(populate_existing=True))

    async def get_active_by_suite(self, suite_id: str) -> PerfSuiteRun | None:
        return await self.session.scalar(
            select(PerfSuiteRun)
            .where(
                PerfSuiteRun.suite_id == suite_id,
                PerfSuiteRun.status.in_(["queued", "running", "stopping"]),
            )
            .order_by(PerfSuiteRun.created_at.desc(), PerfSuiteRun.id.desc())
            .limit(1)
        )

    async def latest_by_suite(self, suite_id: str) -> PerfSuiteRun | None:
        return await self.session.scalar(
            select(PerfSuiteRun)
            .where(PerfSuiteRun.suite_id == suite_id)
            .order_by(PerfSuiteRun.created_at.desc(), PerfSuiteRun.id.desc())
            .limit(1)
        )

    async def latest_by_suites(self, suite_ids: list[str]) -> dict[str, PerfSuiteRun]:
        """Select only the newest run per suite for list summaries."""
        if not suite_ids:
            return {}
        latest = latest_per_resource(
            select(PerfSuiteRun).where(PerfSuiteRun.suite_id.in_(suite_ids)),
            PerfSuiteRun.suite_id,
            PerfSuiteRun.created_at,
            PerfSuiteRun.id,
        )
        rows = (await self.session.scalars(latest)).all()
        return {row.suite_id: row for row in rows}

    async def list_active(self, *, limit: int = 100) -> list[PerfSuiteRun]:
        return list(
            (
                await self.session.scalars(
                    select(PerfSuiteRun)
                    .where(PerfSuiteRun.status.in_(["queued", "running", "stopping"]))
                    .order_by(PerfSuiteRun.id.asc())
                    .limit(limit)
                )
            ).all()
        )

    async def list_by_project(
        self,
        project_id: str,
        *,
        suite_id: str = "",
        status: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[PerfSuiteRun], int]:
        conditions = [PerfSuiteRun.project_id == project_id]
        if suite_id:
            conditions.append(PerfSuiteRun.suite_id == suite_id)
        if status:
            conditions.append(PerfSuiteRun.status == status)
        total = await self.session.scalar(
            select(func.count()).select_from(PerfSuiteRun).where(*conditions)
        )
        rows = list(
            (
                await self.session.scalars(
                    select(PerfSuiteRun)
                    .where(*conditions)
                    .order_by(PerfSuiteRun.created_at.desc(), PerfSuiteRun.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        return rows, int(total or 0)

    async def list_items(self, suite_run_id: str) -> list[PerfSuiteRunItem]:
        return list(
            (
                await self.session.scalars(
                    select(PerfSuiteRunItem)
                    .where(PerfSuiteRunItem.suite_run_id == suite_run_id)
                    .order_by(PerfSuiteRunItem.order_no.asc(), PerfSuiteRunItem.id.asc())
                )
            ).all()
        )

    async def get_item_by_child_run(self, child_run_id: str) -> PerfSuiteRunItem | None:
        return await self.session.scalar(
            select(PerfSuiteRunItem).where(PerfSuiteRunItem.child_run_id == child_run_id)
        )

    def add(self, run: PerfSuiteRun) -> None:
        self.session.add(run)

    def add_item(self, item: PerfSuiteRunItem) -> None:
        self.session.add(item)

    async def refresh(self, run: PerfSuiteRun) -> None:
        await self.session.refresh(run)
