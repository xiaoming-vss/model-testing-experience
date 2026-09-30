from __future__ import annotations

from sqlalchemy import func, select

from testing_agent.models.bug import Bug
from testing_agent.models.bug_activity import BugActivity
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.project import Project
from testing_agent.models.project_member import ProjectMember
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.test_order import TestOrder
from testing_agent.models.test_order_entry import TestOrderEntry
from testing_agent.repositories.base import ResourceRepository


class BugRepository(ResourceRepository):
    model = Bug
    id_column = "bug_id"

    async def get_bug(self, bug_id: str) -> Bug | None:
        return await self.session.scalar(select(Bug).where(Bug.bug_id == bug_id))

    async def get_project(self, project_id: str) -> Project | None:
        return await self.session.scalar(select(Project).where(Project.project_id == project_id))

    async def get_project_member(self, project_id: str, user_id: str) -> ProjectMember | None:
        return await self.session.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
        )

    async def get_sprint(self, sprint_id: str) -> Sprint | None:
        return await self.session.scalar(select(Sprint).where(Sprint.sprint_id == sprint_id))

    async def get_requirement(self, requirement_id: str) -> Requirement | None:
        return await self.session.scalar(
            select(Requirement).where(Requirement.requirement_id == requirement_id)
        )

    async def get_order(self, order_id: str) -> TestOrder | None:
        return await self.session.scalar(select(TestOrder).where(TestOrder.order_id == order_id))

    async def get_entry(self, entry_id: str) -> TestOrderEntry | None:
        return await self.session.scalar(
            select(TestOrderEntry).where(TestOrderEntry.entry_id == entry_id)
        )

    async def get_case_title(self, case_id: str) -> str:
        return (
            await self.session.scalar(
                select(FunctionTestCase.title).where(FunctionTestCase.case_id == case_id)
            )
        ) or ""

    async def next_bug_no(self, project_id: str) -> int:
        """项目内自增编号：取当前最大值加一，冲突由调用方重试。"""
        current = await self.session.scalar(
            select(func.max(Bug.bug_no)).where(Bug.project_id == project_id)
        )
        return int(current or 0) + 1

    async def resolve_requirement_names(self, bugs: list[Bug]) -> None:
        requirement_ids = sorted({bug.requirement_id for bug in bugs if bug.requirement_id})
        if not requirement_ids:
            return
        rows = (
            await self.session.execute(
                select(Requirement.requirement_id, Requirement.name).where(
                    Requirement.requirement_id.in_(requirement_ids)
                )
            )
        ).all()
        names: dict[str, str] = {row[0]: row[1] for row in rows}
        for bug in bugs:
            bug.requirement_name = names.get(bug.requirement_id, "")

    async def list_by_query(
        self,
        project_id: str,
        *,
        statuses: list[str],
        severity: str,
        assignee_user_id: str,
        sprint_id: str,
        sprint_filter: str,
        source_entry_id: str,
        keyword: str,
        page: int,
        page_size: int,
    ) -> tuple[list[Bug], int]:
        conditions = [Bug.project_id == project_id]
        if statuses:
            conditions.append(Bug.status.in_(statuses))
        if severity:
            conditions.append(Bug.severity == severity)
        if assignee_user_id:
            conditions.append(Bug.assignee_user_id == assignee_user_id)
        # 迭代筛选支持两种口径：发现迭代（默认）与计划修复迭代。
        if sprint_id:
            column = (
                Bug.planned_fix_sprint_id if sprint_filter == "planned_fix" else Bug.found_sprint_id
            )
            conditions.append(column == sprint_id)
        if source_entry_id:
            conditions.append(Bug.source_entry_id == source_entry_id)
        if keyword:
            keyword = keyword.strip()
            if keyword.isdigit():
                conditions.append(Bug.title.like(f"%{keyword}%") | (Bug.bug_no == int(keyword)))
            else:
                conditions.append(Bug.title.like(f"%{keyword}%"))
        total = int(await self.session.scalar(select(func.count(Bug.id)).where(*conditions)) or 0)
        rows = list(
            (
                await self.session.scalars(
                    select(Bug)
                    .where(*conditions)
                    .order_by(Bug.created_at.desc(), Bug.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        await self.resolve_requirement_names(rows)
        return rows, total

    def add(self, bug: Bug) -> None:
        self.session.add(bug)

    def add_activity(self, activity: BugActivity) -> None:
        self.session.add(activity)

    async def list_activities(self, bug_id: str) -> list[BugActivity]:
        return list(
            (
                await self.session.scalars(
                    select(BugActivity)
                    .where(BugActivity.bug_id == bug_id)
                    .order_by(BugActivity.created_at.asc(), BugActivity.id.asc())
                )
            ).all()
        )
