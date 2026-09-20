from __future__ import annotations

from sqlalchemy import func, select

from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
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
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_case_run import UiTestCaseRun
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.base import ResourceRepository


class AiGenerateTaskRepository(ResourceRepository):
    async def commit(self) -> None:
        from testing_agent.services.ai_execution import persist

        await self.session.run_sync(persist)
        await self.session.commit()

    async def _project_run(self, row):
        from testing_agent.services.ai_execution import project

        return await self.session.run_sync(lambda session: project(session, row))

    model = AiGenerateTask
    id_column = "task_id"

    async def get_project(self, project_id: str) -> Project | None:
        return await self.session.scalar(
            select(Project).where(Project.project_id == project_id).with_for_update()
        )

    async def get_sprint(self, sprint_id: str) -> Sprint | None:
        return await self.session.scalar(
            select(Sprint).where(Sprint.sprint_id == sprint_id).with_for_update()
        )

    async def get_requirement(self, requirement_id: str) -> Requirement | None:
        return await self.session.scalar(
            select(Requirement)
            .where(
                Requirement.requirement_id == requirement_id,
            )
            .with_for_update()
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

    async def list_api_cases(self, collection_id: str) -> list[ApiCase]:
        return list(
            (
                await self.session.scalars(
                    select(ApiCase).where(
                        ApiCase.collection_id == collection_id,
                    )
                )
            ).all()
        )

    async def list_api_extract_rules(self, case_id: str) -> list[ApiExtractRule]:
        return list(
            (
                await self.session.scalars(
                    select(ApiExtractRule)
                    .where(
                        ApiExtractRule.case_id == case_id,
                    )
                    .order_by(ApiExtractRule.order_no, ApiExtractRule.id)
                )
            ).all()
        )

    async def list_api_assert_rules(self, case_id: str) -> list[ApiAssertRule]:
        return list(
            (
                await self.session.scalars(
                    select(ApiAssertRule)
                    .where(
                        ApiAssertRule.case_id == case_id,
                    )
                    .order_by(ApiAssertRule.order_no, ApiAssertRule.id)
                )
            ).all()
        )

    async def get_task(self, task_id: str) -> AiGenerateTask | None:
        return await self.session.scalar(
            select(AiGenerateTask).where(
                AiGenerateTask.task_id == task_id,
            )
        )

    async def list_tasks(self, project_id: str, task_type: str) -> list[AiGenerateTask]:
        return list(
            (
                await self.session.scalars(
                    select(AiGenerateTask)
                    .where(
                        AiGenerateTask.project_id == project_id,
                        AiGenerateTask.task_type == task_type,
                    )
                    .order_by(AiGenerateTask.created_at.desc())
                )
            ).all()
        )

    async def get_active_task_by_project_sprint_type(
        self, project_id: str, sprint_id: str, task_type: str
    ) -> AiGenerateTask | None:
        return await self.session.scalar(
            select(AiGenerateTask).where(
                AiGenerateTask.project_id == project_id,
                AiGenerateTask.sprint_id == sprint_id,
                AiGenerateTask.task_type == task_type,
            )
        )

    async def get_task_by_order_type(self, order_id: str, task_type: str) -> AiGenerateTask | None:
        """测试单域任务按测试单定位；同迭代可以有多张测试单，(project, sprint) 定位不到。"""
        return await self.session.scalar(
            select(AiGenerateTask).where(
                AiGenerateTask.order_id == order_id,
                AiGenerateTask.task_type == task_type,
            )
        )

    async def list_runs_by_project_sprint_task_type(
        self, project_id: str, sprint_id: str, task_type: str
    ) -> list[AiGenerateTaskRun]:
        rows = list(
            (
                await self.session.scalars(
                    select(AiGenerateTaskRun)
                    .join(AiGenerateTask, AiGenerateTask.task_id == AiGenerateTaskRun.task_id)
                    .where(
                        AiGenerateTask.project_id == project_id,
                        AiGenerateTask.sprint_id == sprint_id,
                        AiGenerateTask.task_type == task_type,
                    )
                    .order_by(AiGenerateTaskRun.created_at.desc())
                )
            ).all()
        )
        from testing_agent.services.ai_execution import project_many

        return await self.session.run_sync(lambda session: project_many(session, rows))

    async def get_run(self, run_id: str) -> AiGenerateTaskRun | None:
        row = await self.session.scalar(
            select(AiGenerateTaskRun).where(AiGenerateTaskRun.run_id == run_id).with_for_update()
        )
        return await self._project_run(row)

    async def get_run_for_update(self, run_id: str) -> AiGenerateTaskRun | None:
        row = await self.session.scalar(
            select(AiGenerateTaskRun)
            .where(AiGenerateTaskRun.run_id == run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return await self._project_run(row)

    async def list_runs(self, task_id: str) -> list[AiGenerateTaskRun]:
        rows = list(
            (
                await self.session.scalars(
                    select(AiGenerateTaskRun)
                    .where(AiGenerateTaskRun.task_id == task_id)
                    .order_by(AiGenerateTaskRun.created_at.desc())
                )
            ).all()
        )
        from testing_agent.services.ai_execution import project_many

        return await self.session.run_sync(lambda session: project_many(session, rows))

    async def get_latest_worker_task_by_run_id(self, run_id: str) -> WorkerTask | None:
        row = await self.session.scalar(
            select(WorkerTask)
            .where(WorkerTask.domain == "ai", WorkerTask.run_id == run_id)
            .order_by(WorkerTask.created_at.desc(), WorkerTask.id.desc())
        )

        from testing_agent.services.worker_context import hydrate

        return await self.session.run_sync(lambda session: hydrate(session, row))

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
        )

    async def get_function_case_by_suite_and_title(
        self, suite_id: str, title: str
    ) -> FunctionTestCase | None:
        return await self.session.scalar(
            select(FunctionTestCase).where(
                FunctionTestCase.suite_id == suite_id,
                FunctionTestCase.title == title,
            )
        )

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
                )
            ).all()
        )

    async def list_function_suites_by_requirement(
        self, requirement_id: str
    ) -> list[FunctionTestSuite]:
        return list(
            (
                await self.session.scalars(
                    select(FunctionTestSuite)
                    .where(
                        FunctionTestSuite.requirement_id == requirement_id,
                    )
                    .order_by(FunctionTestSuite.created_at.asc(), FunctionTestSuite.id.asc())
                )
            ).all()
        )

    async def list_api_collections_by_requirement(self, requirement_id: str) -> list[ApiCollection]:
        return list(
            (
                await self.session.scalars(
                    select(ApiCollection)
                    .where(
                        ApiCollection.requirement_id == requirement_id,
                    )
                    .order_by(ApiCollection.created_at.asc(), ApiCollection.id.asc())
                )
            ).all()
        )

    async def list_ui_suites_by_requirement(self, requirement_id: str) -> list[UiTestSuite]:
        return list(
            (
                await self.session.scalars(
                    select(UiTestSuite)
                    .where(
                        UiTestSuite.requirement_id == requirement_id,
                    )
                    .order_by(UiTestSuite.created_at.asc(), UiTestSuite.id.asc())
                )
            ).all()
        )

    async def get_latest_api_case_run(self, case_id: str) -> ApiCaseRun | None:
        """该用例最近一次 run(创建时间最新在前,同刻取 id 较大者,结果确定)。"""
        return await self.session.scalar(
            select(ApiCaseRun)
            .where(ApiCaseRun.case_id == case_id)
            .order_by(ApiCaseRun.created_at.desc(), ApiCaseRun.id.desc())
            .limit(1)
        )

    async def get_latest_ui_case_run(self, case_id: str) -> UiTestCaseRun | None:
        """该用例最近一次 run(创建时间最新在前,同刻取 id 较大者,结果确定)。"""
        return await self.session.scalar(
            select(UiTestCaseRun)
            .where(UiTestCaseRun.case_id == case_id)
            .order_by(UiTestCaseRun.created_at.desc(), UiTestCaseRun.id.desc())
            .limit(1)
        )

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
