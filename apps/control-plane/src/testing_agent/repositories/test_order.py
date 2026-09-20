from __future__ import annotations

from sqlalchemy import func, select

from testing_agent.core.enums import TestOrderEntryStatus
from testing_agent.domain.test_order_status import derive_test_order_status
from testing_agent.models.project import Project
from testing_agent.models.project_member import ProjectMember
from testing_agent.models.sprint import Sprint
from testing_agent.models.test_order import TestOrder
from testing_agent.models.test_order_entry import TestOrderEntry
from testing_agent.repositories.base import ResourceRepository


class TestOrderRepository(ResourceRepository):
    model = TestOrder
    id_column = "order_id"

    async def get_sprint(self, sprint_id: str) -> Sprint | None:
        return await self.session.scalar(select(Sprint).where(Sprint.sprint_id == sprint_id))

    async def get_project(self, project_id: str) -> Project | None:
        return await self.session.scalar(select(Project).where(Project.project_id == project_id))

    async def get_project_member(self, project_id: str, user_id: str) -> ProjectMember | None:
        return await self.session.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
        )

    async def _with_progress(self, orders: list[TestOrder]) -> list[TestOrder]:
        """一次聚合查询把每个测试单的条目进度挂到对象上，避免逐单查询。"""
        order_ids = [order.order_id for order in orders]
        counts: dict[str, dict[str, int]] = {}
        if order_ids:
            rows = (
                await self.session.execute(
                    select(
                        TestOrderEntry.order_id,
                        TestOrderEntry.status,
                        func.count(TestOrderEntry.id),
                    )
                    .where(TestOrderEntry.order_id.in_(order_ids))
                    .group_by(TestOrderEntry.order_id, TestOrderEntry.status)
                )
            ).all()
            for order_id, status, count in rows:
                counts.setdefault(order_id, {})[status] = count
        for order in orders:
            by_status = counts.get(order.order_id, {})
            total = sum(by_status.values())
            executed = total - by_status.get(TestOrderEntryStatus.PENDING.value, 0)
            order.entries_total = total
            order.entries_executed = executed
            order.entries_passed = by_status.get(TestOrderEntryStatus.PASSED.value, 0)
            order.entries_failed = by_status.get(TestOrderEntryStatus.FAILED.value, 0)
            order.entries_blocked = by_status.get(TestOrderEntryStatus.BLOCKED.value, 0)
            order.entries_skipped = by_status.get(TestOrderEntryStatus.SKIPPED.value, 0)
            order.status = derive_test_order_status(total, executed)
        return orders

    async def get_order(self, order_id: str) -> TestOrder | None:
        order = await self.session.scalar(select(TestOrder).where(TestOrder.order_id == order_id))
        if order is None:
            return None
        return (await self._with_progress([order]))[0]

    async def list_by_project(self, project_id: str, *, sprint_id: str = "") -> list[TestOrder]:
        statement = select(TestOrder).where(TestOrder.project_id == project_id)
        if sprint_id:
            statement = statement.where(TestOrder.sprint_id == sprint_id)
        orders = list(
            (
                await self.session.scalars(
                    statement.order_by(TestOrder.created_at.desc(), TestOrder.id.desc())
                )
            ).all()
        )
        return await self._with_progress(orders)

    def add(self, order: TestOrder) -> None:
        self.session.add(order)

    async def refresh(self, order: TestOrder) -> None:
        await self.session.refresh(order)
