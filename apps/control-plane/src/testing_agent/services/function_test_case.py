from __future__ import annotations

import builtins
from typing import Any

from testing_agent.core.errors import (
    ErrNotFound,
)
from testing_agent.core.sid import new_id
from testing_agent.domain.function_case_content import CaseContent, set_legacy_content
from testing_agent.domain.function_case_query import FunctionCaseQuery
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.repositories.function_test_case import FunctionTestCaseRepository
from testing_agent.schemas.function_test_case import (
    FunctionCaseLibraryItem,
    FunctionCaseRequest,
    FunctionCaseResponse,
)
from testing_agent.services.common import apply_patch, dump, list_payload, paged_payload
from testing_agent.services.function_case_access import FunctionCaseAccess
from testing_agent.services.project_access import (
    require_project_id,
)
from testing_agent.services.resource_deletion import ResourceDeletion, SqlResourceDeletion


class FunctionTestCaseService:
    def __init__(
        self,
        repository: FunctionTestCaseRepository,
        *,
        deletion: ResourceDeletion | None = None,
    ) -> None:
        self.repository = repository
        self.access = FunctionCaseAccess(repository)
        self.deletion = deletion or SqlResourceDeletion()

    async def create(self, user_id: str, suite_id: str, body: FunctionCaseRequest) -> dict:
        await self.access.get_accessible_suite(user_id, suite_id, action="write")
        case = FunctionTestCase(
            case_id=new_id(),
            suite_id=suite_id,
            **body.model_dump(by_alias=False),
        )
        self.repository.add(case)
        await self.repository.commit()
        await self.repository.refresh(case)
        return dump(FunctionCaseResponse, case)

    async def list(self, user_id: str, suite_id: str) -> dict[str, Any]:
        await self.access.get_accessible_suite(user_id, suite_id, action="read")
        rows = await self.repository.list_by_suite(suite_id)
        return list_payload([dump(FunctionCaseResponse, row) for row in rows])

    async def list_project_cases(self, user_id: str, query: FunctionCaseQuery) -> dict[str, Any]:
        """项目范围内的用例检索：跨迭代 / 需求 / 测试集筛选并分页。"""
        await require_project_id(self.repository.session, user_id, query.project_id, action="read")
        cases, total = await self.repository.list_by_project(query)
        return paged_payload([dump(FunctionCaseLibraryItem, case) for case in cases], total)

    async def get(self, user_id: str, case_id: str) -> dict:
        return dump(
            FunctionCaseResponse,
            await self.access.get_accessible_entity(user_id, case_id, action="read"),
        )

    async def update(self, user_id: str, case_id: str, body: dict[str, Any]) -> dict:
        case = await self.access.get_accessible_entity(user_id, case_id, action="write")
        body = dict(body)
        structured = body.pop("content", None)
        legacy = {}
        for key, alias in (
            ("preconditions", "preconditions"),
            ("steps", "steps"),
            ("expected_results", "expectedResults"),
        ):
            if key in body:
                legacy[key] = body.pop(key)
            elif alias in body:
                legacy[key] = body.pop(alias)
        if structured is not None:
            case.content_json = CaseContent.model_validate(structured).model_dump()
        elif legacy:
            set_legacy_content(
                case,
                **{
                    key: legacy.get(key, getattr(case, key))
                    for key in ("preconditions", "steps", "expected_results")
                },
            )
        apply_patch(
            case,
            body,
            {
                "module",
                "title",
                "preconditions",
                "steps",
                "expected_results",
                "priority",
                "case_type",
                "order_no",
            },
        )
        await self.repository.commit()
        await self.repository.refresh(case)
        return dump(FunctionCaseResponse, case)

    async def batch_delete(self, user_id: str, suite_id: str, case_ids: builtins.list[str]) -> dict:
        await self.access.get_accessible_suite(user_id, suite_id, action="write")
        cases = []
        for case_id in case_ids:
            case = await self.repository.get_case(case_id)
            if case is None or case.suite_id != suite_id:
                raise ErrNotFound()
            cases.append(case)
        try:
            for case in cases:
                await self.deletion.delete(self.repository.session, case)
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        return {"deletedIds": case_ids, "deletedCount": len(case_ids)}

    async def delete(self, user_id: str, case_id: str) -> dict:
        case = await self.access.get_accessible_entity(user_id, case_id, action="write")
        await self.deletion.delete(self.repository.session, case)
        await self.repository.commit()
        return {}
