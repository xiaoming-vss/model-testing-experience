from __future__ import annotations

from sqlalchemy import select

from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.repositories.base import ResourceRepository


class UiTestCaseRepository(ResourceRepository):
    model = UiTestCase
    id_column = "case_id"

    async def get_requirement(self, requirement_id: str) -> Requirement | None:
        return await self.session.scalar(
            select(Requirement).where(
                Requirement.requirement_id == requirement_id,
            )
        )

    async def get_sprint(self, sprint_id: str) -> Sprint | None:
        return await self.session.scalar(select(Sprint).where(Sprint.sprint_id == sprint_id))

    async def get_project(self, project_id: str) -> Project | None:
        return await self.session.scalar(select(Project).where(Project.project_id == project_id))

    async def get_suite(self, suite_id: str) -> UiTestSuite | None:
        return await self.session.scalar(
            select(UiTestSuite).where(
                UiTestSuite.suite_id == suite_id,
            )
        )

    async def get_case(self, case_id: str) -> UiTestCase | None:
        return await self.session.scalar(
            select(UiTestCase).where(
                UiTestCase.case_id == case_id,
            )
        )

    async def list_by_suite(self, suite_id: str) -> list[UiTestCase]:
        return list(
            (
                await self.session.scalars(
                    select(UiTestCase)
                    .where(UiTestCase.suite_id == suite_id)
                    .order_by(UiTestCase.order_no)
                )
            ).all()
        )

    def add(self, case: UiTestCase) -> None:
        self.session.add(case)

    async def refresh(self, case: UiTestCase) -> None:
        await self.session.refresh(case)
