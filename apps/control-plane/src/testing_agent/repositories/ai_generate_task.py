from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import load_only

from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.api_assert_rule import ApiAssertRule
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.api_extract_rule import ApiExtractRule
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.test_order import TestOrder
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_case_run import UiTestCaseRun
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.repositories.auxiliary_execution import latest_task_status_subquery
from testing_agent.repositories.base import ResourceRepository

TASK_SUMMARY_COLUMNS = (
    AiGenerateTask.task_id,
    AiGenerateTask.task_type,
    AiGenerateTask.name,
    AiGenerateTask.project_id,
    AiGenerateTask.sprint_id,
    AiGenerateTask.requirement_id,
    AiGenerateTask.order_id,
    AiGenerateTask.execution_entry_id,
    AiGenerateTask.creator_user_id,
    AiGenerateTask.source_type,
    AiGenerateTask.interface_ids_json,
    AiGenerateTask.instruction,
    AiGenerateTask.created_at,
    AiGenerateTask.updated_at,
)


def project_ui_source_cases(rows: Iterable[tuple[FunctionTestCase, str]]) -> list[dict[str, Any]]:
    """Keep the UI generation and source-verification projections identical."""
    return [
        {
            "caseId": case.case_id,
            "suiteId": case.suite_id,
            "suiteName": name,
            "module": case.module,
            "title": case.title,
            "priority": case.priority,
            "caseType": case.case_type,
            "content": deepcopy(case.content_json),
        }
        for case, name in rows
    ]


class AiGenerateTaskRepository(ResourceRepository):
    model = AiGenerateTask
    id_column = "task_id"

    async def list_ui_source_cases(
        self, requirement_id: str, case_ids: list[str] | None = None
    ) -> list[dict]:
        query = (
            select(FunctionTestCase, FunctionTestSuite.name)
            .join(FunctionTestSuite, FunctionTestCase.suite_id == FunctionTestSuite.suite_id)
            .where(
                FunctionTestSuite.requirement_id == requirement_id,
                FunctionTestCase.invalidated_at.is_(None),
            )
            .order_by(FunctionTestSuite.id, FunctionTestCase.order_no, FunctionTestCase.id)
        )
        if case_ids is not None:
            query = query.where(FunctionTestCase.case_id.in_(case_ids))
        rows = (await self.session.execute(query)).all()
        return project_ui_source_cases((row[0], row[1]) for row in rows)

    async def get_project(self, project_id: str) -> Project | None:
        return await self.session.scalar(select(Project).where(Project.project_id == project_id))

    async def get_project_for_update(self, project_id: str) -> Project | None:
        return await self.session.scalar(
            select(Project)
            .where(Project.project_id == project_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def get_sprint(self, sprint_id: str) -> Sprint | None:
        return await self.session.scalar(select(Sprint).where(Sprint.sprint_id == sprint_id))

    async def get_test_order(self, order_id: str) -> TestOrder | None:
        return await self.session.scalar(select(TestOrder).where(TestOrder.order_id == order_id))

    async def get_sprint_for_update(self, sprint_id: str) -> Sprint | None:
        return await self.session.scalar(
            select(Sprint)
            .where(Sprint.sprint_id == sprint_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def get_requirement(self, requirement_id: str) -> Requirement | None:
        return await self.session.scalar(
            select(Requirement).where(Requirement.requirement_id == requirement_id)
        )

    async def get_requirement_for_update(self, requirement_id: str) -> Requirement | None:
        return await self.session.scalar(
            select(Requirement)
            .where(Requirement.requirement_id == requirement_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def get_collection(self, collection_id: str) -> ApiCollection | None:
        return await self.session.scalar(
            select(ApiCollection).where(
                ApiCollection.collection_id == collection_id,
            )
        )

    async def exists_case_by_collection_and_name(self, collection_id: str, name: str) -> bool:
        row = await self.session.scalar(
            select(ApiCase.case_id).where(
                ApiCase.collection_id == collection_id,
                ApiCase.name == name,
            )
        )
        return row is not None

    async def list_api_cases(
        self, collection_id: str, *, for_update: bool = False
    ) -> list[ApiCase]:
        query = select(ApiCase).where(ApiCase.collection_id == collection_id)
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        return list((await self.session.scalars(query)).all())

    async def list_api_extract_rules(
        self, case_id: str, *, for_update: bool = False
    ) -> list[ApiExtractRule]:
        query = (
            select(ApiExtractRule)
            .where(ApiExtractRule.case_id == case_id)
            .order_by(ApiExtractRule.order_no, ApiExtractRule.id)
        )
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        return list((await self.session.scalars(query)).all())

    async def list_api_assert_rules(
        self, case_id: str, *, for_update: bool = False
    ) -> list[ApiAssertRule]:
        query = (
            select(ApiAssertRule)
            .where(ApiAssertRule.case_id == case_id)
            .order_by(ApiAssertRule.order_no, ApiAssertRule.id)
        )
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        return list((await self.session.scalars(query)).all())

    async def get_task(self, task_id: str) -> AiGenerateTask | None:
        return await self.session.scalar(
            select(AiGenerateTask).where(
                AiGenerateTask.task_id == task_id,
            )
        )

    async def get_task_for_update(self, task_id: str) -> AiGenerateTask | None:
        return await self.session.scalar(
            select(AiGenerateTask)
            .where(AiGenerateTask.task_id == task_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def task_scope_resources(self, tasks):
        """Load scope references in batches instead of querying each list item."""
        requirement_ids = {task.requirement_id for task in tasks if task.requirement_id}
        requirements = (
            {
                row.requirement_id: row
                for row in await self.session.execute(
                    select(Requirement.requirement_id, Requirement.sprint_id).where(
                        Requirement.requirement_id.in_(requirement_ids)
                    )
                )
            }
            if requirement_ids
            else {}
        )
        sprint_ids = {task.sprint_id for task in tasks if task.sprint_id}
        sprint_ids.update(row.sprint_id for row in requirements.values())
        sprints = (
            {
                row.sprint_id: row
                for row in await self.session.execute(
                    select(Sprint.sprint_id, Sprint.project_id).where(
                        Sprint.sprint_id.in_(sprint_ids)
                    )
                )
            }
            if sprint_ids
            else {}
        )
        # ``order_id`` is only present on test-order anchored tasks; other callers
        # pass lightweight namespaces without that attribute.
        order_ids = {getattr(task, "order_id", "") or "" for task in tasks}
        order_ids.discard("")
        orders = (
            {
                row.order_id: row
                for row in await self.session.execute(
                    select(TestOrder.order_id, TestOrder.project_id, TestOrder.sprint_id).where(
                        TestOrder.order_id.in_(order_ids)
                    )
                )
            }
            if order_ids
            else {}
        )
        return requirements, sprints, orders

    @staticmethod
    def _keyword_pattern(keyword: str) -> str:
        escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    def _task_conditions(
        self,
        project_id: str,
        task_type: str,
        *,
        sprint_id: str,
        requirement_id: str,
        keyword: str,
    ):
        conditions = [
            AiGenerateTask.project_id == project_id,
            AiGenerateTask.task_type == task_type,
        ]
        if sprint_id:
            conditions.append(AiGenerateTask.sprint_id == sprint_id)
        if requirement_id:
            conditions.append(AiGenerateTask.requirement_id == requirement_id)
        joins = []
        keyword = keyword.strip()
        if keyword:
            pattern = self._keyword_pattern(keyword)
            joins = [
                (Sprint, Sprint.sprint_id == AiGenerateTask.sprint_id),
                (Requirement, Requirement.requirement_id == AiGenerateTask.requirement_id),
            ]
            conditions.append(
                or_(
                    AiGenerateTask.name.like(pattern, escape="\\"),
                    Sprint.name.like(pattern, escape="\\"),
                    Requirement.name.like(pattern, escape="\\"),
                )
            )
        return conditions, joins

    @staticmethod
    def _apply_joins(statement, joins):
        for target, onclause in joins:
            statement = statement.outerjoin(target, onclause)
        return statement

    async def count_tasks(
        self,
        project_id: str,
        task_type: str,
        *,
        sprint_id: str = "",
        requirement_id: str = "",
        keyword: str = "",
        status_values: tuple[str, ...] | None = None,
    ) -> int:
        conditions, joins = self._task_conditions(
            project_id,
            task_type,
            sprint_id=sprint_id,
            requirement_id=requirement_id,
            keyword=keyword,
        )
        statement = select(func.count(AiGenerateTask.id)).select_from(AiGenerateTask)
        statement = self._apply_joins(statement, joins)
        if status_values is not None:
            latest = latest_task_status_subquery(project_id, task_type)
            statement = statement.outerjoin(
                latest, latest.c.task_id == AiGenerateTask.task_id
            ).where(latest.c.latest_run_status.in_(status_values))
        statement = statement.where(*conditions)
        return int(await self.session.scalar(statement) or 0)

    async def list_tasks_page(
        self,
        project_id: str,
        task_type: str,
        *,
        sprint_id: str = "",
        requirement_id: str = "",
        keyword: str = "",
        status_values: tuple[str, ...] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[tuple[AiGenerateTask, str]]:
        conditions, joins = self._task_conditions(
            project_id,
            task_type,
            sprint_id=sprint_id,
            requirement_id=requirement_id,
            keyword=keyword,
        )
        latest = latest_task_status_subquery(project_id, task_type)
        statement = (
            select(AiGenerateTask, latest.c.latest_run_status)
            .options(load_only(*TASK_SUMMARY_COLUMNS))
            .select_from(AiGenerateTask)
        )
        statement = statement.outerjoin(latest, latest.c.task_id == AiGenerateTask.task_id)
        statement = self._apply_joins(statement, joins)
        statement = statement.where(*conditions)
        if status_values is not None:
            statement = statement.where(latest.c.latest_run_status.in_(status_values))
        statement = (
            statement.order_by(AiGenerateTask.created_at.desc(), AiGenerateTask.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.session.execute(statement)).all()
        return [(row[0], row[1] or "") for row in rows]

    async def task_status_counts(
        self,
        project_id: str,
        task_type: str,
        *,
        sprint_id: str = "",
        requirement_id: str = "",
        keyword: str = "",
    ) -> dict[str, int]:
        conditions, joins = self._task_conditions(
            project_id,
            task_type,
            sprint_id=sprint_id,
            requirement_id=requirement_id,
            keyword=keyword,
        )
        latest = latest_task_status_subquery(project_id, task_type)
        statement = (
            select(latest.c.latest_run_status, func.count(AiGenerateTask.id))
            .select_from(AiGenerateTask)
            .outerjoin(latest, latest.c.task_id == AiGenerateTask.task_id)
        )
        statement = self._apply_joins(statement, joins)
        statement = statement.where(*conditions).group_by(latest.c.latest_run_status)
        rows = (await self.session.execute(statement)).all()
        return {("" if status is None else str(status)): int(count) for status, count in rows}

    async def get_active_task_by_project_sprint_type(
        self, project_id: str, sprint_id: str, task_type: str
    ) -> AiGenerateTask | None:
        return await self.session.scalar(
            select(AiGenerateTask)
            .where(
                AiGenerateTask.project_id == project_id,
                AiGenerateTask.sprint_id == sprint_id,
                AiGenerateTask.task_type == task_type,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def get_task_by_project_sprint_type(
        self, project_id: str, sprint_id: str, task_type: str
    ) -> AiGenerateTask | None:
        return await self.session.scalar(
            select(AiGenerateTask).where(
                AiGenerateTask.project_id == project_id,
                AiGenerateTask.sprint_id == sprint_id,
                AiGenerateTask.task_type == task_type,
            )
        )

    async def get_task_by_order_type(
        self, order_id: str, task_type: str, *, current_read: bool = False
    ) -> AiGenerateTask | None:
        """测试单域任务按测试单定位；派发时使用当前读。"""
        statement = select(AiGenerateTask).where(
            AiGenerateTask.order_id == order_id,
            AiGenerateTask.task_type == task_type,
        )
        if current_read:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return await self.session.scalar(statement)

    async def get_function_suite_by_requirement_and_name(
        self, requirement_id: str, name: str
    ) -> FunctionTestSuite | None:
        return await self.session.scalar(
            select(FunctionTestSuite)
            .where(
                FunctionTestSuite.requirement_id == requirement_id,
                FunctionTestSuite.name == name,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def get_function_suite(self, suite_id: str) -> FunctionTestSuite | None:
        return await self.session.scalar(
            select(FunctionTestSuite).where(FunctionTestSuite.suite_id == suite_id)
        )

    async def get_case(self, case_id: str, *, for_update: bool = False) -> FunctionTestCase | None:
        """Look up a fixed case ID across suites before adopting a candidate ID."""
        query = select(FunctionTestCase).where(FunctionTestCase.case_id == case_id)
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        return await self.session.scalar(query)

    async def list_function_cases(self, suite_id: str) -> list[FunctionTestCase]:
        return list(
            (
                await self.session.scalars(
                    select(FunctionTestCase)
                    .where(
                        FunctionTestCase.suite_id == suite_id,
                    )
                    .order_by(FunctionTestCase.order_no, FunctionTestCase.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        )

    async def max_function_case_order_by_suite(self, suite_id: str) -> int:
        value = await self.session.scalar(
            select(func.max(FunctionTestCase.order_no)).where(
                FunctionTestCase.suite_id == suite_id,
            )
        )
        return int(value or 0)

    async def get_ui_suite(self, suite_id: str) -> UiTestSuite | None:
        return await self.session.scalar(
            select(UiTestSuite)
            .where(
                UiTestSuite.suite_id == suite_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def list_ui_cases(self, suite_id: str) -> list[UiTestCase]:
        return list(
            (
                await self.session.scalars(
                    select(UiTestCase)
                    .where(
                        UiTestCase.suite_id == suite_id,
                    )
                    .order_by(UiTestCase.order_no, UiTestCase.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        )

    async def list_requirement_case_pairs(self, requirement_id: str, kind: str):
        models: dict[
            str,
            tuple[
                type[FunctionTestCase] | type[ApiCase] | type[UiTestCase],
                type[FunctionTestSuite] | type[ApiCollection] | type[UiTestSuite],
                str,
            ],
        ] = {
            "function": (FunctionTestCase, FunctionTestSuite, "suite_id"),
            "api": (ApiCase, ApiCollection, "collection_id"),
            "ui": (UiTestCase, UiTestSuite, "suite_id"),
        }
        case, parent, parent_key = models[kind]
        rows = await self.session.execute(
            select(case, parent)
            .join(parent, getattr(parent, parent_key) == getattr(case, parent_key))
            .where(
                parent.requirement_id == requirement_id,
                case.invalidated_at.is_(None),
            )
            .order_by(parent.created_at, parent.id, case.order_no, case.id)
        )
        return list(rows.all())

    async def list_api_assert_rules_for_cases(self, case_ids: list[str]):
        if not case_ids:
            return []
        return list(
            (
                await self.session.scalars(
                    select(ApiAssertRule)
                    .where(ApiAssertRule.case_id.in_(case_ids))
                    .order_by(ApiAssertRule.order_no, ApiAssertRule.id)
                )
            ).all()
        )

    async def latest_case_run_summaries(self, case_ids: list[str], kind: str):
        from testing_agent.repositories.latest import latest_per_resource

        if not case_ids:
            return {}
        model = ApiCaseRun if kind == "api" else UiTestCaseRun
        rows = await self.session.execute(
            latest_per_resource(
                select(model.case_id, model.status, model.finished_at).where(
                    model.case_id.in_(case_ids), model.trigger_type != "live_debug"
                ),
                model.case_id,
                model.created_at,
                model.id,
            )
        )
        return {row.case_id: row for row in rows.all()}

    def add(self, row: object) -> None:
        self.session.add(row)

    def add_all(self, rows: list[object]) -> None:
        self.session.add_all(rows)

    async def delete(self, row: object) -> None:
        await self.session.delete(row)

    async def rollback(self) -> None:
        await self.session.rollback()

    async def refresh(self, row: object) -> None:
        await self.session.refresh(row)
