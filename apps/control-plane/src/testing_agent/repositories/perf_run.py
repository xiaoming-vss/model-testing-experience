from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import load_only

from testing_agent.models.perf_run import PerfRun
from testing_agent.repositories.base import ResourceRepository

SUMMARY_COLUMNS = (
    PerfRun.run_id,
    PerfRun.case_id,
    PerfRun.project_id,
    PerfRun.sprint_id,
    PerfRun.sprint_name,
    PerfRun.case_version,
    PerfRun.case_name,
    PerfRun.environment_id,
    PerfRun.environment_name,
    PerfRun.monitoring_connection_id,
    PerfRun.monitoring_connection_name,
    PerfRun.trigger_user_id,
    PerfRun.trigger_type,
    PerfRun.status,
    PerfRun.outcome,
    PerfRun.flags_json,
    PerfRun.error_message,
    PerfRun.k6_version,
    PerfRun.template_version,
    PerfRun.script_sha256,
    PerfRun.started_at,
    PerfRun.finished_at,
    PerfRun.duration_ms,
    PerfRun.created_at,
)


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
                    .options(load_only(*SUMMARY_COLUMNS))
                    .where(*conditions)
                    .order_by(PerfRun.created_at.desc(), PerfRun.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        return rows, int(total or 0)

    async def list_by_ids(
        self, run_ids: list[str], *, for_update: bool = False
    ) -> dict[str, PerfRun]:
        if not run_ids:
            return {}
        query = select(PerfRun).where(PerfRun.run_id.in_(run_ids))
        if for_update:
            query = query.with_for_update()
        rows = list((await self.session.scalars(query)).all())
        return {row.run_id: row for row in rows}

    def add(self, run: PerfRun) -> None:
        self.session.add(run)

    async def refresh(self, run: PerfRun) -> None:
        await self.session.refresh(run)
