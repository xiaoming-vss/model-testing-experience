from __future__ import annotations

import builtins

from sqlalchemy import select

from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.models.sprint import Sprint
from testing_agent.models.sprint_daily_metrics import SprintDailyMetrics
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.models.ui_test_suite_run import UiTestSuiteRun
from testing_agent.repositories.base import BaseRepository


class SprintDailyMetricsRepository(BaseRepository):
    async def get_sprint(self, sprint_id: str) -> Sprint | None:
        return await self.session.scalar(select(Sprint).where(Sprint.sprint_id == sprint_id))

    async def get_project(self, project_id: str) -> Project | None:
        return await self.session.scalar(select(Project).where(Project.project_id == project_id))

    async def list(
        self,
        sprint_id: str,
        start_date: str = "",
        end_date: str = "",
    ) -> builtins.list[SprintDailyMetrics]:
        stmt = select(SprintDailyMetrics).where(SprintDailyMetrics.sprint_id == sprint_id)
        if start_date:
            stmt = stmt.where(SprintDailyMetrics.snapshot_date >= start_date)
        if end_date:
            stmt = stmt.where(SprintDailyMetrics.snapshot_date <= end_date)
        rows = await self.session.scalars(stmt.order_by(SprintDailyMetrics.snapshot_date.asc()))
        return list(rows.all())

    async def get(self, sprint_id: str, snapshot_date: str) -> SprintDailyMetrics | None:
        return await self.session.scalar(
            select(SprintDailyMetrics).where(
                SprintDailyMetrics.sprint_id == sprint_id,
                SprintDailyMetrics.snapshot_date == snapshot_date,
            )
        )

    async def list_requirements_by_sprint(self, sprint_id: str) -> builtins.list[Requirement]:
        return list(
            (
                await self.session.scalars(
                    select(Requirement)
                    .where(
                        Requirement.sprint_id == sprint_id,
                    )
                    .order_by(Requirement.id.asc())
                )
            ).all()
        )

    async def list_api_case_ids_by_sprint(self, sprint_id: str) -> builtins.list[str]:
        return list(
            (
                await self.session.scalars(
                    select(ApiCase.case_id)
                    .join(ApiCollection, ApiCollection.collection_id == ApiCase.collection_id)
                    .join(Requirement, Requirement.requirement_id == ApiCollection.requirement_id)
                    .where(
                        Requirement.sprint_id == sprint_id,
                    )
                    .order_by(ApiCase.id.asc())
                )
            ).all()
        )

    async def list_latest_api_run_statuses(self, sprint_id: str) -> dict[str, str]:
        runs = list(
            (
                await self.session.scalars(
                    select(ApiCaseRun)
                    .join(ApiCollection, ApiCollection.collection_id == ApiCaseRun.collection_id)
                    .join(Requirement, Requirement.requirement_id == ApiCollection.requirement_id)
                    .join(ApiCase, ApiCase.case_id == ApiCaseRun.case_id)
                    .where(
                        Requirement.sprint_id == sprint_id,
                        ApiCase.collection_id == ApiCollection.collection_id,
                    )
                    .order_by(
                        ApiCaseRun.case_id.asc(),
                        ApiCaseRun.created_at.desc(),
                        ApiCaseRun.id.desc(),
                    )
                )
            ).all()
        )
        statuses: dict[str, str] = {}
        for run in runs:
            statuses.setdefault(run.case_id, run.status)
        return statuses

    async def list_ui_case_ids_by_sprint(self, sprint_id: str) -> builtins.list[str]:
        return list(
            (
                await self.session.scalars(
                    select(UiTestCase.case_id)
                    .join(UiTestSuite, UiTestSuite.suite_id == UiTestCase.suite_id)
                    .join(Requirement, Requirement.requirement_id == UiTestSuite.requirement_id)
                    .where(
                        Requirement.sprint_id == sprint_id,
                    )
                    .order_by(UiTestCase.id.asc())
                )
            ).all()
        )

    async def list_latest_ui_suite_runs(self, sprint_id: str) -> builtins.list[UiTestSuiteRun]:
        runs = list(
            (
                await self.session.scalars(
                    select(UiTestSuiteRun)
                    .join(UiTestSuite, UiTestSuite.suite_id == UiTestSuiteRun.suite_id)
                    .join(Requirement, Requirement.requirement_id == UiTestSuite.requirement_id)
                    .where(
                        Requirement.sprint_id == sprint_id,
                    )
                    .order_by(
                        UiTestSuiteRun.suite_id.asc(),
                        UiTestSuiteRun.created_at.desc(),
                        UiTestSuiteRun.id.desc(),
                    )
                )
            ).all()
        )
        latest_runs: dict[str, UiTestSuiteRun] = {}
        for run in runs:
            latest_runs.setdefault(run.suite_id, run)
        return list(latest_runs.values())

    async def get_active_binding(
        self,
        resource_type: str,
        resource_id: str,
    ) -> ResourceBinding | None:
        return await self.session.scalar(
            select(ResourceBinding)
            .where(
                ResourceBinding.local_resource_type == resource_type,
                ResourceBinding.local_resource_id == resource_id,
                ResourceBinding.status == "active",
                ResourceBinding.provider == "zentao",
            )
            .order_by(ResourceBinding.id.asc())
        )

    def add(self, metric: SprintDailyMetrics) -> None:
        self.session.add(metric)

    async def refresh(self, metric: SprintDailyMetrics) -> None:
        await self.session.refresh(metric)
