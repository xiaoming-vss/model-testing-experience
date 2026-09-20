from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError

from testing_agent.core.enums import TEST_ORDER_ENTRY_TERMINAL_STATUSES, TestOrderEntryStatus
from testing_agent.core.errors import (
    ErrBadRequest,
    ErrFunctionTestCaseNotFound,
    ErrTestOrderAssigneeInvalid,
    ErrTestOrderCaseMismatch,
    ErrTestOrderEntryAssigneeLocked,
    ErrTestOrderEntryDuplicate,
    ErrTestOrderEntryNotFound,
)
from testing_agent.core.sid import new_id
from testing_agent.domain.function_case_content import CaseContent
from testing_agent.models.test_order import TestOrder
from testing_agent.models.test_order_entry import TestOrderEntry
from testing_agent.repositories.test_order_entry import FUNCTION_CASE_TYPE, TestOrderEntryRepository
from testing_agent.schemas.test_order import TestOrderEntryResponse
from testing_agent.services.common import dump, list_payload
from testing_agent.services.project_access import ProjectAction
from testing_agent.services.test_order import TestOrderService

EMPTY_CASE_CONTENT: dict[str, Any] = {"preconditions": [], "steps": []}


class TestOrderEntryService:
    def __init__(
        self,
        repository: TestOrderEntryRepository,
        test_order_service: TestOrderService,
    ) -> None:
        self.repository = repository
        self.orders = test_order_service

    async def ensure_order_access(
        self, user_id: str, order_id: str, *, action: ProjectAction = "read"
    ) -> TestOrder:
        return await self.orders.get_accessible_entity(user_id, order_id, action=action)

    async def add_cases(self, user_id: str, order_id: str, case_ids: list[str]) -> dict:
        """把用例库里的用例加入测试单：快照加入时的内容，已存在的跳过。"""
        order = await self.ensure_order_access(user_id, order_id, action="write")
        rows = await self.repository.list_function_cases_with_scope(case_ids)
        cases: dict[str, Any] = {}
        for case, _suite, _requirement, sprint in rows:
            if sprint.project_id != order.project_id:
                raise ErrTestOrderCaseMismatch
            cases[case.case_id] = case
        if any(case_id not in cases for case_id in case_ids):
            raise ErrFunctionTestCaseNotFound

        existing = await self.repository.list_existing_case_ids(order_id)
        order_no = await self.repository.next_order_no(order_id)
        created: list[TestOrderEntry] = []
        skipped = 0
        for case_id in case_ids:
            if case_id in existing:
                skipped += 1
                continue
            case = cases[case_id]
            snapshot = CaseContent.model_validate(case.content_json or EMPTY_CASE_CONTENT)
            created.append(
                TestOrderEntry(
                    entry_id=new_id(),
                    order_id=order_id,
                    case_type=FUNCTION_CASE_TYPE,
                    case_id=case_id,
                    order_no=order_no,
                    snapshot_json=snapshot.model_dump(),
                    status=TestOrderEntryStatus.PENDING.value,
                )
            )
            order_no += 1
            existing.add(case_id)
        if created:
            self.repository.add_all(created)
            try:
                await self.repository.commit()
            except IntegrityError as exc:
                await self.repository.rollback()
                raise ErrTestOrderEntryDuplicate from exc
        return {"addedCount": len(created), "skippedCount": skipped}

    async def update(
        self, user_id: str, order_id: str, entry_id: str, body: dict[str, Any]
    ) -> dict:
        """即时保存一条执行结果；已分配的条目只有该执行人（或项目所有者）能改。"""
        entry = await self.repository.get_entry(entry_id)
        if entry is None or entry.order_id != order_id:
            raise ErrTestOrderEntryNotFound
        _order, role = await self.orders.get_accessible_entity_with_role(
            user_id, order_id, action="execute"
        )
        if entry.assignee_user_id and entry.assignee_user_id != user_id and role != "owner":
            raise ErrTestOrderEntryAssigneeLocked

        for field in ("actual_results", "failure_reason", "block_reason", "zentao_bug_id"):
            value = body.get(field)
            if value is not None:
                setattr(entry, field, str(value).strip())

        status = body.get("status")
        if status is not None:
            status = str(status).strip()
            if status not in TestOrderEntryStatus.values():
                raise ErrBadRequest
            entry.status = status

        if entry.status in TEST_ORDER_ENTRY_TERMINAL_STATUSES:
            entry.executor_user_id = user_id
            entry.executed_at = datetime.now(UTC)
        await self.repository.commit()
        return dump(TestOrderEntryResponse, entry)

    async def batch_mark_passed(self, user_id: str, order_id: str, entry_ids: list[str]) -> dict:
        """批量标记通过：只对未执行的条目生效，并把每个步骤都记为通过。"""
        _order, role = await self.orders.get_accessible_entity_with_role(
            user_id, order_id, action="execute"
        )
        entries = await self.repository.list_by_ids(order_id, entry_ids)
        if len(entries) != len(entry_ids):
            raise ErrTestOrderEntryNotFound
        for entry in entries:
            if entry.assignee_user_id and entry.assignee_user_id != user_id and role != "owner":
                raise ErrTestOrderEntryAssigneeLocked
        marked = 0
        for entry in entries:
            if entry.status != TestOrderEntryStatus.PENDING.value:
                continue
            entry.status = TestOrderEntryStatus.PASSED.value
            entry.executor_user_id = user_id
            entry.executed_at = datetime.now(UTC)
            marked += 1
        await self.repository.commit()
        return {"markedCount": marked, "skippedCount": len(entries) - marked}

    async def list(self, user_id: str, order_id: str) -> dict[str, Any]:
        await self.ensure_order_access(user_id, order_id, action="read")
        entries = await self.repository.list_by_order(order_id)
        return list_payload([dump(TestOrderEntryResponse, entry) for entry in entries])

    async def assign(
        self,
        user_id: str,
        order_id: str,
        entry_ids: list[str],
        assignee_user_id: str,
    ) -> dict[str, Any]:
        """分配执行人：仅项目所有者，空串表示取消分配。"""
        order = await self.ensure_order_access(user_id, order_id, action="manage")
        assignee = assignee_user_id.strip()
        if assignee and not await self.orders.is_assignable_member(order.project_id, assignee):
            raise ErrTestOrderAssigneeInvalid
        entries = await self.repository.list_by_ids(order_id, entry_ids)
        if len(entries) != len(entry_ids):
            raise ErrTestOrderEntryNotFound
        for entry in entries:
            entry.assignee_user_id = assignee
        await self.repository.commit()
        return list_payload([dump(TestOrderEntryResponse, entry) for entry in entries])

    async def delete(self, user_id: str, order_id: str, entry_id: str) -> dict:
        entry = await self.repository.get_entry(entry_id)
        if entry is None or entry.order_id != order_id:
            raise ErrTestOrderEntryNotFound
        await self.ensure_order_access(user_id, order_id, action="write")
        await self.repository.hard_delete(entry)
        await self.repository.commit()
        return {}
