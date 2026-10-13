from __future__ import annotations

import builtins
from datetime import datetime
from typing import TypedDict

from sqlalchemy import select

from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.bug import Bug
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.models.sprint import Sprint
from testing_agent.models.sprint_daily_metrics import SprintDailyMetrics
from testing_agent.models.test_order import TestOrder
from testing_agent.models.test_order_entry import TestOrderEntry
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.models.ui_test_suite_run import UiTestSuiteRun
from testing_agent.repositories.base import BaseRepository
from testing_agent.repositories.latest import latest_per_resource


class BugSnapshot(TypedDict):
    bugId: str
    bugNo: int
    title: str
    status: str
    severity: str
    resolution: str


class SprintDailyMetricsRepository(BaseRepository):
    async def get_sprint(self, sprint_id: str) -> Sprint | None:
        return await self.session.scalar(select(Sprint).where(Sprint.sprint_id == sprint_id))

    async def lock_sprint(self, sprint_id: str) -> Sprint | None:
        return await self.session.scalar(
            select(Sprint).where(Sprint.sprint_id == sprint_id).with_for_update()
        )

    async def list_running_sprint_ids(self, now: datetime) -> builtins.list[str]:
        return list(
            (
                await self.session.scalars(
                    select(Sprint.sprint_id)
                    .where(Sprint.start_time <= now, Sprint.end_time > now)
                    .order_by(Sprint.id)
                )
            ).all()
        )

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

    async def get(
        self, sprint_id: str, snapshot_date: str, *, for_update: bool = False
    ) -> SprintDailyMetrics | None:
        stmt = select(SprintDailyMetrics).where(
            SprintDailyMetrics.sprint_id == sprint_id,
            SprintDailyMetrics.snapshot_date == snapshot_date,
        )
        if for_update:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def list_bug_snapshots(
        self, project_id: str, sprint_id: str
    ) -> builtins.list[BugSnapshot]:
        """与平台 Bug 列表默认的发现迭代筛选一致，读取报告所需摘要。"""
        rows = await self.session.execute(
            select(Bug.bug_id, Bug.bug_no, Bug.title, Bug.status, Bug.severity, Bug.resolution)
            .where(Bug.project_id == project_id, Bug.found_sprint_id == sprint_id)
            .order_by(Bug.created_at.desc(), Bug.id.desc())
        )
        return [
            BugSnapshot(
                bugId=bug_id,
                bugNo=bug_no,
                title=title,
                status=status,
                severity=severity,
                resolution=resolution,
            )
            for bug_id, bug_no, title, status, severity, resolution in rows
        ]

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

    async def list_function_entry_statuses_by_sprint(self, sprint_id: str) -> builtins.list[str]:
        """功能用例的执行状态来自测试单条目（本地记录），不再走禅道。"""
        return list(
            (
                await self.session.scalars(
                    select(TestOrderEntry.status)
                    .join(TestOrder, TestOrder.order_id == TestOrderEntry.order_id)
                    .where(TestOrder.sprint_id == sprint_id)
                )
            ).all()
        )

    async def list_latest_api_run_statuses(self, sprint_id: str) -> dict[str, str]:
        statement = (
            select(ApiCaseRun.case_id, ApiCaseRun.status)
            .join(ApiCollection, ApiCollection.collection_id == ApiCaseRun.collection_id)
            .join(Requirement, Requirement.requirement_id == ApiCollection.requirement_id)
            .join(ApiCase, ApiCase.case_id == ApiCaseRun.case_id)
            .where(
                Requirement.sprint_id == sprint_id,
                ApiCase.collection_id == ApiCollection.collection_id,
            )
        )
        rows = await self.session.execute(
            latest_per_resource(statement, ApiCaseRun.case_id, ApiCaseRun.created_at, ApiCaseRun.id)
        )
        return {case_id: status for case_id, status in rows}

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

    async def list_latest_ui_suite_runs(self, sprint_id: str) -> builtins.list:
        statement = (
            select(
                UiTestSuiteRun.suite_id,
                UiTestSuiteRun.total_count,
                UiTestSuiteRun.success_count,
                UiTestSuiteRun.failed_count,
                UiTestSuiteRun.error_count,
                UiTestSuiteRun.skipped_count,
            )
            .join(UiTestSuite, UiTestSuite.suite_id == UiTestSuiteRun.suite_id)
            .join(Requirement, Requirement.requirement_id == UiTestSuite.requirement_id)
            .where(Requirement.sprint_id == sprint_id)
        )
        rows = await self.session.execute(
            latest_per_resource(
                statement, UiTestSuiteRun.suite_id, UiTestSuiteRun.created_at, UiTestSuiteRun.id
            )
        )
        return list(rows.all())

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
