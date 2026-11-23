from __future__ import annotations

from collections.abc import Sequence

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

    async def list_by_suite(
        self, suite_id: str, *, invalidated: bool | None = None
    ) -> list[UiTestCase]:
        conditions = [UiTestCase.suite_id == suite_id]
        if invalidated is True:
            conditions.append(UiTestCase.invalidated_at.is_not(None))
        elif invalidated is False:
            conditions.append(UiTestCase.invalidated_at.is_(None))
        return list(
            (
                await self.session.scalars(
                    select(UiTestCase).where(*conditions).order_by(UiTestCase.order_no)
                )
            ).all()
        )

    async def list_project_cases_by_ids(
        self, project_id: str, case_ids: Sequence[str]
    ) -> list[UiTestCase]:
        """按项目范围加载选中用例并锁定状态列，供批量失效/恢复正常事务使用。"""
        cases: list[UiTestCase] = []
        for offset in range(0, len(case_ids), 500):
            cases.extend(
                (
                    await self.session.scalars(
                        select(UiTestCase)
                        .join(UiTestSuite, UiTestSuite.suite_id == UiTestCase.suite_id)
                        .where(
                            UiTestSuite.project_id == project_id,
                            UiTestCase.case_id.in_(case_ids[offset : offset + 500]),
                        )
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                ).all()
            )
        return cases

    def add(self, case: UiTestCase) -> None:
        self.session.add(case)

    async def refresh(self, case: UiTestCase) -> None:
        await self.session.refresh(case)
