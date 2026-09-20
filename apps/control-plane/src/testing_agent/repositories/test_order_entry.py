from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.test_order import TestOrder
from testing_agent.models.test_order_entry import TestOrderEntry
from testing_agent.repositories.base import ResourceRepository

FUNCTION_CASE_TYPE = "function"


class TestOrderEntryRepository(ResourceRepository):
    model = TestOrderEntry
    id_column = "entry_id"

    async def get_test_order(self, order_id: str) -> TestOrder | None:
        return await self.session.scalar(select(TestOrder).where(TestOrder.order_id == order_id))

    async def get_sprint(self, sprint_id: str) -> Sprint | None:
        return await self.session.scalar(select(Sprint).where(Sprint.sprint_id == sprint_id))

    async def get_entry(self, entry_id: str) -> TestOrderEntry | None:
        return await self.session.scalar(
            select(TestOrderEntry).where(TestOrderEntry.entry_id == entry_id)
        )

    async def list_by_order(self, order_id: str) -> list[TestOrderEntry]:
        """条目按加入顺序返回，并带上被引用用例的当前身份（标题 / 模块 / 优先级）。"""
        entries = list(
            (
                await self.session.scalars(
                    select(TestOrderEntry)
                    .where(TestOrderEntry.order_id == order_id)
                    .order_by(TestOrderEntry.order_no, TestOrderEntry.id)
                )
            ).all()
        )
        case_ids = [
            entry.case_id
            for entry in entries
            if entry.case_type == FUNCTION_CASE_TYPE and entry.case_id
        ]
        if case_ids:
            cases = list(
                (
                    await self.session.scalars(
                        select(FunctionTestCase).where(FunctionTestCase.case_id.in_(case_ids))
                    )
                ).all()
            )
            by_id = {case.case_id: case for case in cases}
            for entry in entries:
                case = by_id.get(entry.case_id)
                if case is None:
                    continue
                entry.case_title = case.title
                entry.case_module = case.module
                entry.case_priority = case.priority
        return entries

    async def list_by_ids(self, order_id: str, entry_ids: list[str]) -> list[TestOrderEntry]:
        return list(
            (
                await self.session.scalars(
                    select(TestOrderEntry).where(
                        TestOrderEntry.order_id == order_id,
                        TestOrderEntry.entry_id.in_(entry_ids),
                    )
                )
            ).all()
        )

    async def list_existing_case_ids(self, order_id: str) -> set[str]:
        return set(
            (
                await self.session.scalars(
                    select(TestOrderEntry.case_id).where(
                        TestOrderEntry.order_id == order_id,
                        TestOrderEntry.case_type == FUNCTION_CASE_TYPE,
                    )
                )
            ).all()
        )

    async def next_order_no(self, order_id: str) -> int:
        current = await self.session.scalar(
            select(func.max(TestOrderEntry.order_no)).where(TestOrderEntry.order_id == order_id)
        )
        return int(current or 0) + 1

    async def list_function_cases_with_scope(self, case_ids: list[str]) -> list[Any]:
        """取用例连同它所属的测试集 / 需求 / 迭代，用于校验用例归属项目。"""
        return list(
            (
                await self.session.execute(
                    select(FunctionTestCase, FunctionTestSuite, Requirement, Sprint)
                    .join(
                        FunctionTestSuite, FunctionTestSuite.suite_id == FunctionTestCase.suite_id
                    )
                    .join(
                        Requirement, Requirement.requirement_id == FunctionTestSuite.requirement_id
                    )
                    .join(Sprint, Sprint.sprint_id == Requirement.sprint_id)
                    .where(FunctionTestCase.case_id.in_(case_ids))
                )
            ).all()
        )

    def add(self, entry: TestOrderEntry) -> None:
        self.session.add(entry)

    def add_all(self, entries: list[TestOrderEntry]) -> None:
        self.session.add_all(entries)
