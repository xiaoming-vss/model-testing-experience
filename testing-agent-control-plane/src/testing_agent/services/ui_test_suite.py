from __future__ import annotations

from typing import Any

from testing_agent.core.errors import ErrNotFound
from testing_agent.core.sid import new_id
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.repositories.ui_test_suite import UiTestSuiteRepository
from testing_agent.schemas.ui_test_suite import UiSuiteRequest, UiSuiteResponse
from testing_agent.services.common import apply_patch, dump, list_payload
from testing_agent.services.project_access import ProjectAction, require_project_access


class UiTestSuiteService:
    def __init__(self, repository: UiTestSuiteRepository):
        self.repository = repository

    async def ensure_requirement_access(
        self, user_id: str, requirement_id: str, *, action: ProjectAction = "read"
    ) -> None:
        requirement = await self.repository.get_requirement(requirement_id)
        if requirement is None:
            raise ErrNotFound
        sprint = await self.repository.get_sprint(requirement.sprint_id)
        if sprint is None:
            raise ErrNotFound
        project = await self.repository.get_project(sprint.project_id)
        if project is None:
            raise ErrNotFound
        await require_project_access(self.repository.session, user_id, project, action)

    async def get_accessible_entity(
        self, user_id: str, suite_id: str, *, action: ProjectAction = "read"
    ) -> UiTestSuite:
        suite = await self.repository.get_suite(suite_id)
        if suite is None:
            raise ErrNotFound
        await self.ensure_requirement_access(user_id, suite.requirement_id, action=action)
        return suite

    async def create(self, user_id: str, requirement_id: str, body: UiSuiteRequest) -> dict:
        await self.ensure_requirement_access(user_id, requirement_id, action="write")
        suite = UiTestSuite(
            suite_id=new_id(),
            requirement_id=requirement_id,
            **body.model_dump(by_alias=False),
        )
        self.repository.add(suite)
        await self.repository.commit()
        await self.repository.refresh(suite)
        return dump(UiSuiteResponse, suite)

    async def list(self, user_id: str, requirement_id: str) -> dict[str, Any]:
        await self.ensure_requirement_access(user_id, requirement_id, action="read")
        rows = await self.repository.list_by_requirement(requirement_id)
        return list_payload([dump(UiSuiteResponse, row) for row in rows])

    async def get(self, user_id: str, suite_id: str) -> dict:
        return dump(
            UiSuiteResponse, await self.get_accessible_entity(user_id, suite_id, action="read")
        )

    async def update(self, user_id: str, suite_id: str, body: dict[str, Any]) -> dict:
        suite = await self.get_accessible_entity(user_id, suite_id, action="write")
        apply_patch(
            suite,
            body,
            {
                "name",
                "description",
                "headless",
                "slow_mo_ms",
                "viewport_width",
                "viewport_height",
                "default_step_timeout_ms",
                "screenshot_policy",
            },
        )
        await self.repository.commit()
        await self.repository.refresh(suite)
        return dump(UiSuiteResponse, suite)

    async def delete(self, user_id: str, suite_id: str) -> dict:
        suite = await self.get_accessible_entity(user_id, suite_id, action="write")
        await self.repository.hard_delete(suite)
        await self.repository.commit()
        return {}
