from __future__ import annotations

from sqlalchemy import func, or_, select

from testing_agent.domain.function_case_query import FunctionCaseQuery
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.models.sprint import Sprint
from testing_agent.repositories.base import ResourceRepository


class FunctionTestCaseRepository(ResourceRepository):
    model = FunctionTestCase
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

    async def get_suite(self, suite_id: str) -> FunctionTestSuite | None:
        return await self.session.scalar(
            select(FunctionTestSuite).where(
                FunctionTestSuite.suite_id == suite_id,
            )
        )

    async def list_suites_by_ids(self, suite_ids: list[str]) -> list[FunctionTestSuite]:
        return list(
            (
                await self.session.scalars(
                    select(FunctionTestSuite).where(
                        FunctionTestSuite.suite_id.in_(suite_ids),
                    )
                )
            ).all()
        )

    async def get_case(self, case_id: str) -> FunctionTestCase | None:
        return await self.session.scalar(
            select(FunctionTestCase).where(
                FunctionTestCase.case_id == case_id,
            )
        )

    async def list_by_suite(self, suite_id: str) -> list[FunctionTestCase]:
        return list(
            (
                await self.session.scalars(
                    select(FunctionTestCase)
                    .where(
                        FunctionTestCase.suite_id == suite_id,
                    )
                    .order_by(FunctionTestCase.order_no)
                )
            ).all()
        )

    async def list_by_project(self, query: FunctionCaseQuery) -> tuple[list[FunctionTestCase], int]:
        """按用例库检索条件取一页用例，并把所属测试集 / 需求 / 迭代挂到用例上供响应复用。"""
        conditions = [Sprint.project_id == query.project_id]
        if query.sprint_id:
            conditions.append(Requirement.sprint_id == query.sprint_id)
        if query.requirement_id:
            conditions.append(FunctionTestSuite.requirement_id == query.requirement_id)
        if query.suite_id:
            conditions.append(FunctionTestCase.suite_id == query.suite_id)
        if query.module:
            conditions.append(FunctionTestCase.module == query.module)
        if query.priority:
            conditions.append(FunctionTestCase.priority == query.priority)
        if query.case_type:
            conditions.append(FunctionTestCase.case_type == query.case_type)
        if query.keyword:
            pattern = f"%{query.keyword}%"
            conditions.append(
                or_(
                    FunctionTestCase.title.like(pattern),
                    FunctionTestCase.module.like(pattern),
                )
            )

        statement = (
            select(FunctionTestCase, FunctionTestSuite, Requirement, Sprint)
            .join(FunctionTestSuite, FunctionTestSuite.suite_id == FunctionTestCase.suite_id)
            .join(Requirement, Requirement.requirement_id == FunctionTestSuite.requirement_id)
            .join(Sprint, Sprint.sprint_id == Requirement.sprint_id)
            .where(*conditions)
        )
        total = await self.session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = (
            await self.session.execute(
                statement.order_by(
                    FunctionTestCase.updated_at.desc(),
                    FunctionTestCase.id.desc(),
                )
                .limit(query.limit)
                .offset(query.offset)
            )
        ).all()
        cases = []
        for case, suite, requirement, sprint in rows:
            case.suite_name = suite.name
            case.requirement_id = requirement.requirement_id
            case.requirement_name = requirement.name
            case.sprint_id = sprint.sprint_id
            case.sprint_name = sprint.name
            cases.append(case)
        return cases, int(total or 0)

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
            .limit(1)
        )

    def add(self, case: FunctionTestCase) -> None:
        self.session.add(case)

    async def refresh(self, case: FunctionTestCase) -> None:
        await self.session.refresh(case)
