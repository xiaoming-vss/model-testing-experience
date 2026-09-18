from __future__ import annotations

from sqlalchemy import select

from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_case_run import UiTestCaseRun
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.models.ui_test_suite_run import UiTestSuiteRun, UiTestSuiteRunItem
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.base import BaseRepository


class UiTestCaseRunRepository(BaseRepository):
    async def get_case(self, case_id: str) -> UiTestCase | None:
        return await self.session.scalar(
            select(UiTestCase).where(
                UiTestCase.case_id == case_id,
            )
        )

    async def get_suite(
        self,
        suite_id: str,
    ) -> UiTestSuite | None:
        stmt = select(UiTestSuite).where(UiTestSuite.suite_id == suite_id)
        return await self.session.scalar(stmt)

    async def get_requirement(
        self,
        requirement_id: str,
    ) -> Requirement | None:
        stmt = select(Requirement).where(Requirement.requirement_id == requirement_id)
        return await self.session.scalar(stmt)

    async def get_sprint(self, sprint_id: str) -> Sprint | None:
        stmt = select(Sprint).where(Sprint.sprint_id == sprint_id)
        return await self.session.scalar(stmt)

    async def get_project(self, project_id: str) -> Project | None:
        return await self.session.scalar(select(Project).where(Project.project_id == project_id))

    async def list_cases(self, suite_id: str) -> list[UiTestCase]:
        return list(
            (
                await self.session.scalars(
                    select(UiTestCase)
                    .where(UiTestCase.suite_id == suite_id)
                    .order_by(UiTestCase.order_no)
                )
            ).all()
        )

    async def get_case_run(self, run_id: str) -> UiTestCaseRun | None:
        return await self.session.scalar(
            select(UiTestCaseRun).where(UiTestCaseRun.run_id == run_id)
        )

    async def get_suite_run(self, suite_run_id: str) -> UiTestSuiteRun | None:
        return await self.session.scalar(
            select(UiTestSuiteRun).where(UiTestSuiteRun.suite_run_id == suite_run_id)
        )

    async def list_suite_runs(self, suite_id: str) -> list[UiTestSuiteRun]:
        return list(
            (
                await self.session.scalars(
                    select(UiTestSuiteRun)
                    .where(UiTestSuiteRun.suite_id == suite_id)
                    .order_by(UiTestSuiteRun.created_at.desc())
                )
            ).all()
        )

    async def list_suite_items(self, suite_run_id: str) -> list[UiTestSuiteRunItem]:
        return list(
            (
                await self.session.scalars(
                    select(UiTestSuiteRunItem)
                    .where(UiTestSuiteRunItem.suite_run_id == suite_run_id)
                    .order_by(UiTestSuiteRunItem.order_no)
                )
            ).all()
        )

    def add_all(self, rows: list[UiTestCaseRun | UiTestSuiteRun | WorkerTask]) -> None:
        self.session.add_all(rows)

    def add(self, row: UiTestSuiteRunItem) -> None:
        self.session.add(row)

    async def refresh(self, row: object) -> None:
        await self.session.refresh(row)
