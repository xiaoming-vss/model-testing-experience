from __future__ import annotations

from typing import Any

from testing_agent.core.errors import ErrNotFound
from testing_agent.core.sid import new_id
from testing_agent.domain.function_case_content import generation_fields
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.repositories.function_test_suite import FunctionTestSuiteRepository
from testing_agent.schemas.function_test_suite import (
    FunctionSuiteCaseViewResponse,
    FunctionSuiteRequest,
    FunctionSuiteResponse,
)
from testing_agent.services.ai_generate_task import requirement_source_content
from testing_agent.services.common import apply_patch, dump, list_payload
from testing_agent.services.project_access import (
    ProjectAction,
    require_project_access,
    require_project_id,
)


def case_view_item(case: FunctionTestCase) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "case_module": case.module,
        "case_title": case.title,
        "case_type": case.case_type,
        "priority": case.priority,
        **generation_fields(case.content_json or {}),
    }


class FunctionTestSuiteService:
    def __init__(self, repository: FunctionTestSuiteRepository):
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
    ) -> FunctionTestSuite:
        suite = await self.repository.get_suite(suite_id)
        if suite is None:
            raise ErrNotFound
        await self.ensure_requirement_access(user_id, suite.requirement_id, action=action)
        return suite

    async def create(self, user_id: str, requirement_id: str, body: FunctionSuiteRequest) -> dict:
        await self.ensure_requirement_access(user_id, requirement_id, action="write")
        suite = FunctionTestSuite(
            suite_id=new_id(),
            requirement_id=requirement_id,
            name=body.name,
            description=body.description,
        )
        self.repository.add(suite)
        await self.repository.commit()
        await self.repository.refresh(suite)
        return dump(FunctionSuiteResponse, suite)

    async def list(self, user_id: str, requirement_id: str) -> dict[str, Any]:
        await self.ensure_requirement_access(user_id, requirement_id, action="read")
        rows = await self.repository.list_by_requirement(requirement_id)
        return list_payload([dump(FunctionSuiteResponse, row) for row in rows])

    async def list_project(
        self,
        user_id: str,
        project_id: str,
        *,
        sprint_id: str = "",
        requirement_id: str = "",
    ) -> dict[str, Any]:
        await require_project_id(self.repository.session, user_id, project_id, action="read")
        rows = await self.repository.list_by_project(
            project_id,
            sprint_id=sprint_id.strip(),
            requirement_id=requirement_id.strip(),
        )
        return list_payload([dump(FunctionSuiteResponse, row) for row in rows])

    async def get(self, user_id: str, suite_id: str) -> dict:
        return dump(
            FunctionSuiteResponse,
            await self.get_accessible_entity(user_id, suite_id, action="read"),
        )

    async def requirement_case_view(self, user_id: str, suite_id: str) -> dict:
        """测试集的需求-用例视图：用例还原为生成契约，需求与映射只含测试集所属迭代。"""
        suite = await self.get_accessible_entity(user_id, suite_id, action="read")
        cases = await self.repository.list_cases(suite.suite_id)
        requirements: list[dict[str, Any]] = []
        links: list[dict[str, Any]] = []
        if cases:
            requirement = await self.repository.get_requirement(suite.requirement_id)
            if requirement is not None:
                requirements.append(
                    {
                        "requirement_id": requirement.requirement_id,
                        "requirement_title": requirement.name,
                        "requirement_content": requirement_source_content(requirement),
                    }
                )
            links.append(
                {
                    "requirement_id": suite.requirement_id,
                    "case_ids": [case.case_id for case in cases],
                }
            )
        return dump(
            FunctionSuiteCaseViewResponse,
            {
                "requirements": requirements,
                "cases": [case_view_item(case) for case in cases],
                "case_requirement_links": links,
            },
        )

    async def update(self, user_id: str, suite_id: str, body: dict[str, Any]) -> dict:
        suite = await self.get_accessible_entity(user_id, suite_id, action="write")
        apply_patch(suite, body, {"name", "description"})
        await self.repository.commit()
        await self.repository.refresh(suite)
        return dump(FunctionSuiteResponse, suite)

    async def delete(self, user_id: str, suite_id: str) -> dict:
        suite = await self.get_accessible_entity(user_id, suite_id, action="write")
        await self.repository.hard_delete(suite)
        await self.repository.commit()
        return {}
