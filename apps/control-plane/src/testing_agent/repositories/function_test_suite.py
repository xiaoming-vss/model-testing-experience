from __future__ import annotations

from sqlalchemy import func, select

from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.repositories.base import ResourceRepository


class FunctionTestSuiteRepository(ResourceRepository):
    model = FunctionTestSuite
    id_column = "suite_id"

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

    async def _with_case_counts(self, stmt):
        count = (
            select(func.count(FunctionTestCase.id))
            .where(
                FunctionTestCase.suite_id == FunctionTestSuite.suite_id,
            )
            .correlate(FunctionTestSuite)
            .scalar_subquery()
        )
        rows = (await self.session.execute(stmt.add_columns(count))).all()
        result = []
        for suite, case_count in rows:
            suite.case_count = case_count
            result.append(suite)
        return result

    async def get_suite(self, suite_id: str) -> FunctionTestSuite | None:
        rows = await self._with_case_counts(
            select(FunctionTestSuite).where(
                FunctionTestSuite.suite_id == suite_id,
            )
        )
        return rows[0] if rows else None

    async def list_by_requirement(self, requirement_id: str) -> list[FunctionTestSuite]:
        return await self._with_case_counts(
            select(FunctionTestSuite)
            .where(
                FunctionTestSuite.requirement_id == requirement_id,
            )
            .order_by(FunctionTestSuite.created_at.desc())
        )

    async def list_by_project(
        self,
        project_id: str,
        *,
        sprint_id: str = "",
        requirement_id: str = "",
    ) -> list[FunctionTestSuite]:
        statement = (
            select(FunctionTestSuite)
            .join(Requirement, Requirement.requirement_id == FunctionTestSuite.requirement_id)
            .join(Sprint, Sprint.sprint_id == Requirement.sprint_id)
            .where(Sprint.project_id == project_id)
        )
        if sprint_id:
            statement = statement.where(Requirement.sprint_id == sprint_id)
        if requirement_id:
            statement = statement.where(FunctionTestSuite.requirement_id == requirement_id)
        return await self._with_case_counts(
            statement.order_by(FunctionTestSuite.created_at.desc(), FunctionTestSuite.id.desc())
        )

    def add(self, suite: FunctionTestSuite) -> None:
        self.session.add(suite)

    async def refresh(self, suite: FunctionTestSuite) -> None:
        await self.session.refresh(suite)
