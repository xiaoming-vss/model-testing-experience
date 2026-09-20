from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError

from testing_agent.core.enums import TestOrderEntryStatus
from testing_agent.core.errors import (
    AppError,
    ErrNotFound,
    ErrTestOrderNameAlreadyUse,
    ErrTestOrderSourceMismatch,
)
from testing_agent.core.sid import new_id
from testing_agent.models.sprint import Sprint
from testing_agent.models.test_order import TestOrder
from testing_agent.models.test_order_entry import TestOrderEntry
from testing_agent.repositories.test_order import TestOrderRepository
from testing_agent.repositories.test_order_entry import TestOrderEntryRepository
from testing_agent.schemas.test_order import TestOrderRequest, TestOrderResponse
from testing_agent.services.common import apply_patch, dump, list_payload
from testing_agent.services.project_access import ProjectAction, require_project_access


def _name_conflict_error(exc: IntegrityError) -> AppError | None:
    """只翻译测试单名称这一个业务唯一键，其余数据库错误照旧抛出。"""
    detail = str(exc.orig)
    if "uk_test_order_sprint_name" in detail or (
        "UNIQUE constraint failed: test_orders.sprint_id, test_orders.name" in detail
    ):
        return ErrTestOrderNameAlreadyUse
    return None


class TestOrderService:
    def __init__(
        self,
        repository: TestOrderRepository,
        entry_repository: TestOrderEntryRepository,
    ) -> None:
        self.repository = repository
        self.entry_repository = entry_repository

    async def ensure_sprint_access(
        self, user_id: str, sprint_id: str, *, action: ProjectAction = "read"
    ) -> Sprint:
        sprint = await self.repository.get_sprint(sprint_id)
        if sprint is None:
            raise ErrNotFound
        project = await self.repository.get_project(sprint.project_id)
        if project is None:
            raise ErrNotFound
        await require_project_access(self.repository.session, user_id, project, action)
        return sprint

    async def get_accessible_entity(
        self, user_id: str, order_id: str, *, action: ProjectAction = "read"
    ) -> TestOrder:
        order = await self.repository.get_order(order_id)
        if order is None:
            raise ErrNotFound
        await self.ensure_sprint_access(user_id, order.sprint_id, action=action)
        return order

    async def get_accessible_entity_with_role(
        self, user_id: str, order_id: str, *, action: ProjectAction = "read"
    ) -> tuple[TestOrder, str]:
        """与 get_accessible_entity 相同，但把调用者在项目中的角色一并返回（判定要区分所有者）。"""
        order = await self.repository.get_order(order_id)
        if order is None:
            raise ErrNotFound
        project = await self.repository.get_project(order.project_id)
        if project is None:
            raise ErrNotFound
        role = await require_project_access(self.repository.session, user_id, project, action)
        return order, role

    async def is_assignable_member(self, project_id: str, user_id: str) -> bool:
        """项目所有者不是 project_members 行，因此单独判断。"""
        project = await self.repository.get_project(project_id)
        if project is None:
            return False
        if project.user_id == user_id:
            return True
        return await self.repository.get_project_member(project_id, user_id) is not None

    async def create(self, user_id: str, sprint_id: str, body: TestOrderRequest) -> dict:
        sprint = await self.ensure_sprint_access(user_id, sprint_id, action="write")
        source_order_id = body.source_order_id.strip()
        source_order: TestOrder | None = None
        if source_order_id:
            source_order = await self.repository.get_order(source_order_id)
            if source_order is None:
                raise ErrNotFound
            if source_order.project_id != sprint.project_id:
                raise ErrTestOrderSourceMismatch
        order = TestOrder(
            order_id=new_id(),
            project_id=sprint.project_id,
            sprint_id=sprint.sprint_id,
            name=body.name,
            tested_version=body.tested_version,
        )
        self.repository.add(order)
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            error = _name_conflict_error(exc)
            if error is None:
                raise
            raise error from exc
        if source_order is not None:
            await self._copy_retest_entries(source_order, order)
        return dump(TestOrderResponse, await self.repository.get_order(order.order_id))

    async def _copy_retest_entries(self, source: TestOrder, order: TestOrder) -> None:
        """把来源单里结果非「通过」的条目复制进新单；新单从「未执行」开始，不保留来源关联。"""
        entries = await self.entry_repository.list_by_order(source.order_id)
        retest = [entry for entry in entries if entry.status != TestOrderEntryStatus.PASSED.value]
        if not retest:
            return
        copies = [
            TestOrderEntry(
                entry_id=new_id(),
                order_id=order.order_id,
                case_type=entry.case_type,
                case_id=entry.case_id,
                order_no=index + 1,
                snapshot_json=entry.snapshot_json,
                status=TestOrderEntryStatus.PENDING.value,
            )
            for index, entry in enumerate(retest)
        ]
        self.entry_repository.add_all(copies)
        await self.entry_repository.commit()

    async def list_project(
        self, user_id: str, project_id: str, *, sprint_id: str = ""
    ) -> dict[str, Any]:
        project = await self.repository.get_project(project_id)
        if project is None:
            raise ErrNotFound
        await require_project_access(self.repository.session, user_id, project, action="read")
        orders = await self.repository.list_by_project(project_id, sprint_id=sprint_id.strip())
        return list_payload([dump(TestOrderResponse, order) for order in orders])

    async def get(self, user_id: str, order_id: str) -> dict:
        return dump(
            TestOrderResponse,
            await self.get_accessible_entity(user_id, order_id, action="read"),
        )

    async def update(self, user_id: str, order_id: str, body: dict[str, Any]) -> dict:
        order = await self.get_accessible_entity(user_id, order_id, action="write")
        apply_patch(order, body, {"name", "tested_version"})
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            error = _name_conflict_error(exc)
            if error is None:
                raise
            raise error from exc
        return dump(TestOrderResponse, await self.repository.get_order(order.order_id))

    async def delete(self, user_id: str, order_id: str) -> dict:
        order = await self.get_accessible_entity(user_id, order_id, action="write")
        await self.repository.hard_delete(order)
        await self.repository.commit()
        return {}
