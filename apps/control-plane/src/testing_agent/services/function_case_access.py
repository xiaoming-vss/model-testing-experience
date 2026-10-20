from __future__ import annotations

from testing_agent.core.errors import (
    ErrNotFound,
)
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.repositories.function_test_case import FunctionTestCaseRepository
from testing_agent.services.project_access import (
    ProjectAction,
    require_project_access,
)


class FunctionCaseAccess:
    def __init__(self, repository: FunctionTestCaseRepository) -> None:
        self.repository = repository

    async def get_accessible_suite(
        self, user_id: str, suite_id: str, *, action: ProjectAction = "read"
    ) -> FunctionTestSuite:
        suite, _, _, _ = await self.get_accessible_suite_context(user_id, suite_id, action=action)
        return suite

    async def get_accessible_entity(
        self, user_id: str, case_id: str, *, action: ProjectAction = "read"
    ) -> FunctionTestCase:
        case = await self.repository.get_case(case_id)
        if case is None:
            raise ErrNotFound()
        await self.get_accessible_suite(user_id, case.suite_id, action=action)
        return case

    async def get_accessible_requirement_context(
        self, user_id: str, requirement_id: str, *, action: ProjectAction = "read"
    ) -> tuple[Requirement, Sprint, Project]:
        requirement = await self.repository.get_requirement(requirement_id)
        if requirement is None:
            raise ErrNotFound()
        sprint = await self.repository.get_sprint(requirement.sprint_id)
        if sprint is None:
            raise ErrNotFound()
        project = await self.repository.get_project(sprint.project_id)
        if project is None:
            raise ErrNotFound()
        await require_project_access(self.repository.session, user_id, project, action)
        return requirement, sprint, project

    async def get_accessible_suite_context(
        self, user_id: str, suite_id: str, *, action: ProjectAction = "read"
    ) -> tuple[FunctionTestSuite, Requirement, Sprint, Project]:
        suite = await self.repository.get_suite(suite_id)
        if suite is None:
            raise ErrNotFound()
        requirement, sprint, project = await self.get_accessible_requirement_context(
            user_id, suite.requirement_id, action=action
        )
        return suite, requirement, sprint, project
