from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError

from testing_agent.core.errors import (
    ErrBadRequest,
    ErrNotFound,
    ErrUiTestSuiteNameAlreadyUse,
    dynamic_error,
)
from testing_agent.core.sid import new_id
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.repositories.ui_test_suite import UiTestSuiteRepository
from testing_agent.schemas.ui_test_suite import (
    ProjectUiSuiteRequest,
    UiSuiteRequest,
    UiSuiteResponse,
)
from testing_agent.services.common import apply_patch, dump, list_payload
from testing_agent.services.project_access import (
    ProjectAction,
    require_project_access,
    require_project_id,
    require_requirement_access,
    require_requirement_in_project,
)
from testing_agent.services.resource_deletion import ResourceDeletion, SqlResourceDeletion


class UiTestSuiteService:
    def __init__(
        self, repository: UiTestSuiteRepository, *, deletion: ResourceDeletion | None = None
    ) -> None:
        self.deletion = deletion or SqlResourceDeletion()
        self.repository = repository

    async def ensure_requirement_access(
        self, user_id: str, requirement_id: str, *, action: ProjectAction = "read"
    ) -> None:
        await require_requirement_access(self.repository, user_id, requirement_id, action=action)

    async def get_accessible_entity(
        self, user_id: str, suite_id: str, *, action: ProjectAction = "read"
    ) -> UiTestSuite:
        suite = await self.repository.get_suite(suite_id)
        if suite is None:
            raise ErrNotFound()
        await require_project_id(self.repository.session, user_id, suite.project_id, action=action)
        return suite

    async def create(self, user_id: str, requirement_id: str, body: UiSuiteRequest) -> dict:
        requirement = await self.repository.get_requirement(requirement_id)
        if requirement is None:
            raise ErrNotFound()
        sprint = await self.repository.get_sprint(requirement.sprint_id)
        if sprint is None:
            raise ErrNotFound()
        project = await self.repository.get_project(sprint.project_id)
        if project is None:
            raise ErrNotFound()
        await require_project_access(self.repository.session, user_id, project, "write")
        return await self._create(project.project_id, requirement_id, body)

    async def create_in_project(
        self, user_id: str, project_id: str, body: ProjectUiSuiteRequest
    ) -> dict:
        await require_project_id(self.repository.session, user_id, project_id, action="write")
        requirement_id = body.requirement_id
        if requirement_id is not None:
            await require_requirement_in_project(
                self.repository, user_id, requirement_id, project_id, action="write"
            )
        return await self._create(project_id, requirement_id, body)

    async def _create(
        self, project_id: str, requirement_id: str | None, body: UiSuiteRequest
    ) -> dict:
        payload = body.model_dump(by_alias=False, exclude={"requirement_id"})
        suite = UiTestSuite(
            suite_id=new_id(),
            project_id=project_id,
            requirement_id=requirement_id,
            **payload,
        )
        self.repository.add(suite)
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            if _is_project_name_conflict(exc):
                raise ErrUiTestSuiteNameAlreadyUse() from exc
            raise
        await self.repository.refresh(suite)
        return dump(UiSuiteResponse, suite)

    async def list(self, user_id: str, requirement_id: str) -> dict[str, Any]:
        await self.ensure_requirement_access(user_id, requirement_id, action="read")
        rows = await self.repository.list_by_requirement(requirement_id)
        return list_payload([dump(UiSuiteResponse, row) for row in rows])

    async def list_by_project(self, user_id: str, project_id: str) -> dict[str, Any]:
        await require_project_id(self.repository.session, user_id, project_id, action="read")
        rows = await self.repository.list_by_project(project_id)
        return list_payload([dump(UiSuiteResponse, row) for row in rows])

    async def get(self, user_id: str, suite_id: str) -> dict:
        return dump(
            UiSuiteResponse, await self.get_accessible_entity(user_id, suite_id, action="read")
        )

    async def update(self, user_id: str, suite_id: str, body: dict[str, Any]) -> dict:
        suite = await self.get_accessible_entity(user_id, suite_id, action="write")
        if "requirementId" in body:
            target_id = body["requirementId"]
            if target_id is not None:
                await require_requirement_in_project(
                    self.repository,
                    user_id,
                    target_id,
                    suite.project_id,
                    action="write",
                )
            if target_id != suite.requirement_id:
                if suite.effective_import_id:
                    raise dynamic_error(
                        ErrBadRequest,
                        "已接收生成导入的测试集不能更换或解除需求关联",
                    )
                suite.requirement_id = target_id
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
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            if _is_project_name_conflict(exc):
                raise ErrUiTestSuiteNameAlreadyUse() from exc
            raise
        await self.repository.refresh(suite)
        return dump(UiSuiteResponse, suite)

    async def delete(self, user_id: str, suite_id: str) -> dict:
        suite = await self.get_accessible_entity(user_id, suite_id, action="write")
        await self.deletion.delete(self.repository.session, suite)
        await self.repository.commit()
        return {}


def _is_project_name_conflict(exc: IntegrityError) -> bool:
    detail = str(exc.orig)
    return "uk_ui_suite_project_name" in detail or (
        "UNIQUE constraint failed: ui_test_suites.project_id, ui_test_suites.name" in detail
    )
