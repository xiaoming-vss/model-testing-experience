"""Explicit summary projections; snapshots are available only by entry identity."""

from typing import Any

from sqlalchemy import and_, case, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from testing_agent.domain.test_order_query import EntryQuery
from testing_agent.models.function_test_case import FunctionTestCase as Case
from testing_agent.models.function_test_suite import FunctionTestSuite as Suite
from testing_agent.models.requirement import Requirement
from testing_agent.models.test_order_entry import TestOrderEntry as Entry

STATUSES = ("pending", "passed", "failed", "blocked", "skipped")


def entry_projection(*, detail: bool = False) -> Select[Any]:
    columns = [
        Entry.entry_id,
        Entry.order_id,
        Entry.case_type,
        Entry.case_id,
        Entry.order_no,
        Entry.step_count,
        Entry.status,
        Entry.assignee_user_id,
        Entry.executor_user_id,
        Entry.executed_at,
        Entry.created_at,
        Entry.updated_at,
        func.coalesce(Case.title, "").label("case_title"),
        func.coalesce(Case.module, "").label("case_module"),
        func.coalesce(Case.priority, "").label("case_priority"),
        func.coalesce(Requirement.requirement_id, "").label("requirement_id"),
        func.coalesce(Requirement.name, "").label("requirement_name"),
    ]
    if detail:
        columns += [
            Entry.snapshot_json.label("snapshot"),
            Entry.actual_results,
            Entry.failure_reason,
            Entry.block_reason,
            Entry.zentao_bug_id,
        ]
    return (
        select(*columns)
        .select_from(Entry)
        .outerjoin(Case, and_(Entry.case_type == "function", Case.case_id == Entry.case_id))
        .outerjoin(Suite, Suite.suite_id == Case.suite_id)
        .outerjoin(Requirement, Requirement.requirement_id == Suite.requirement_id)
    )


class TestOrderReadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def detail(self, order_id: str, entry_id: str) -> dict[str, Any] | None:
        row = (
            (
                await self.session.execute(
                    entry_projection(detail=True).where(
                        Entry.order_id == order_id,
                        Entry.entry_id == entry_id,
                    )
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    async def lookup(self, order_id: str, case_ids: list[str]) -> list[dict[str, Any]]:
        result = await self.session.execute(
            entry_projection()
            .where(
                Entry.order_id == order_id,
                Entry.case_type == "function",
                Entry.case_id.in_(case_ids),
            )
            .order_by(Entry.order_no, Entry.id)
        )
        return [dict(row) for row in result.mappings()]

    async def page(self, order_id: str, actor: str, query: EntryQuery) -> dict[str, Any]:
        conditions = [Entry.order_id == order_id]
        if query.only_mine:
            conditions.append(Entry.assignee_user_id == actor)
        if query.keyword.strip():
            text = (
                Entry.case_id
                + " "
                + func.coalesce(Case.title, "")
                + " "
                + func.coalesce(Case.module, "")
            )
            conditions.append(
                func.lower(text).contains(query.keyword.strip().lower(), autoescape=True)
            )
        base = entry_projection().where(*conditions)
        count_base = select(Entry.id).select_from(Entry)
        if query.keyword.strip():
            count_base = count_base.outerjoin(
                Case, and_(Entry.case_type == "function", Case.case_id == Entry.case_id)
            )
        count_base = count_base.where(*conditions)
        rows = await self.session.execute(
            count_base.with_only_columns(
                Entry.status,
                func.count(Entry.id),
                maintain_column_froms=True,
            ).group_by(Entry.status)
        )
        counts = dict.fromkeys(STATUSES, 0)
        counts.update({state: int(count) for state, count in rows})
        matched = sum(counts.values())
        total = counts.get(query.status, 0) if query.status else matched
        global_counts = (
            await self.session.execute(
                select(
                    func.count(Entry.id),
                    func.coalesce(func.sum(case((Entry.assignee_user_id == actor, 1), else_=0)), 0),
                ).where(Entry.order_id == order_id)
            )
        ).one()
        filtered = base.where(Entry.status == query.status) if query.status else base
        page = min(query.page, max(1, (total + query.page_size - 1) // query.page_size))
        filtered_count = (
            count_base.where(Entry.status == query.status) if query.status else count_base
        )
        identity = filtered_count.with_only_columns(
            Entry.entry_id, Entry.order_no, Entry.id, maintain_column_froms=True
        )
        focus = None
        if query.focus_entry_id:
            focus = (
                await self.session.execute(identity.where(Entry.entry_id == query.focus_entry_id))
            ).first()
        elif query.resume:
            candidates = identity
            if query.after_entry_id:
                anchor = (
                    await self.session.execute(
                        select(Entry.order_no, Entry.id).where(
                            Entry.order_id == order_id,
                            Entry.entry_id == query.after_entry_id,
                        )
                    )
                ).first()
                candidates = candidates.where(Entry.status == "pending")
                if anchor is None:
                    candidates = candidates.where(false())
                else:
                    candidates = candidates.where(
                        or_(
                            Entry.order_no > anchor.order_no,
                            and_(Entry.order_no == anchor.order_no, Entry.id > anchor.id),
                        )
                    )
            focus = (
                await self.session.execute(
                    candidates.order_by(
                        case((Entry.status == "pending", 0), else_=1),
                        Entry.order_no,
                        Entry.id,
                    ).limit(1)
                )
            ).first()
        if focus is not None:
            preceding = await self.session.scalar(
                filtered_count.with_only_columns(
                    func.count(Entry.id),
                    maintain_column_froms=True,
                ).where(
                    or_(
                        Entry.order_no < focus.order_no,
                        and_(Entry.order_no == focus.order_no, Entry.id < focus.id),
                    )
                )
            )
            page = int(preceding or 0) // query.page_size + 1
        result = await self.session.execute(
            filtered.order_by(Entry.order_no, Entry.id)
            .offset((page - 1) * query.page_size)
            .limit(query.page_size)
        )
        items = [dict(row) for row in result.mappings()]
        return {
            "items": items,
            "total": total,
            "page": page,
            "pageSize": query.page_size,
            "statusCounts": counts,
            "matchedTotal": matched,
            "orderTotal": int(global_counts[0]),
            "mineCount": int(global_counts[1]),
            "preferredEntryId": focus.entry_id
            if focus
            else (items[0]["entry_id"] if items and not query.after_entry_id else ""),
        }
