from __future__ import annotations

from typing import Any

from testing_agent.core.errors import (
    ErrNotFound,
)
from testing_agent.domain.ai_tasks import (
    task_type_for,
)
from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.ai_generate_task_source_archive import (
    AiGenerateTaskSourceArchiveRepository,
)
from testing_agent.services.ai_task_output import (
    dump_run,
    dump_task,
)
from testing_agent.services.ai_task_scope import GenerationAccess
from testing_agent.services.common import list_payload


class GenerationQueries:
    """Task/detail/history reads through current resource authorization."""

    def __init__(
        self,
        repository: AiGenerateTaskRepository,
        source_archive_repository: AiGenerateTaskSourceArchiveRepository,
        access: GenerationAccess,
    ) -> None:
        self.repository = repository
        self.source_archive_repository = source_archive_repository
        self.access = access

    async def list(self, kind: str, project_id: str, user_id: str) -> dict[str, Any]:
        await self.access.ensure_project_access(user_id, project_id, action="read")
        rows = await self.repository.list_tasks(project_id, task_type_for(kind))
        scope_loader = getattr(self.repository, "task_scope_resources", None)
        scopes = await scope_loader(rows) if scope_loader is not None else None
        payloads = []
        for row in rows:
            await self.access.validate_task_scope(row, scopes)
            archive = (
                await self.source_archive_repository.get_source_archive(row.task_id)
                if kind == "ui"
                else None
            )
            payloads.append(dump_task(row, archive))
        return list_payload(payloads)

    async def get(self, kind: str, task_id: str, user_id: str) -> dict:
        task = await self.access.owned_task(user_id, task_id, kind, action="read")
        archive = (
            await self.source_archive_repository.get_source_archive(task.task_id)
            if kind == "ui"
            else None
        )
        return dump_task(task, archive)

    async def list_run_summaries(
        self,
        kind: str,
        task_id: str,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
        pipeline_filter: str = "all",
    ) -> dict[str, Any]:
        from testing_agent.repositories.ai_run_history import history_page

        await self.access.owned_task(user_id, task_id, kind, action="read")
        return await history_page(
            self.repository.session,
            [AiGenerateTaskRun.task_id == task_id],
            page,
            page_size,
            pipeline_filter,
        )

    async def list_test_report_run_summaries(
        self, project_id: str, sprint_id: str, user_id: str, page: int = 1, page_size: int = 20
    ) -> dict[str, Any]:
        from testing_agent.repositories.ai_run_history import history_page

        await self.access.ensure_project_access(user_id, project_id, action="read")
        sprint = await self.repository.get_sprint(sprint_id)
        if sprint is None or sprint.project_id != project_id:
            raise ErrNotFound()
        return await history_page(
            self.repository.session,
            [
                AiGenerateTask.project_id == project_id,
                AiGenerateTask.sprint_id == sprint_id,
                AiGenerateTask.task_type == task_type_for("test_report"),
            ],
            page,
            page_size,
        )

    async def list_runs(self, kind: str, task_id: str, user_id: str) -> dict[str, Any]:
        await self.access.owned_task(user_id, task_id, kind, action="read")
        rows = await self.repository.list_runs(task_id)
        if kind == "code_risk_analysis":
            # 代码风险分析 run 详情追加解析后的 report 结构(工单 07,RC-5)。
            # 函数级导入避免与 services.ai_generate_task 的模块循环依赖。
            from testing_agent.services.code_risk_analysis import dump_code_risk_analysis_run

            dump = dump_code_risk_analysis_run
        else:
            dump = dump_run
        return list_payload([dump(row) for row in rows])

    async def get_run(self, kind: str, run_id: str, user_id: str) -> dict[str, Any]:
        run = await self.access.owned_run(user_id, run_id, kind, action="read")
        if kind == "code_risk_analysis":
            from testing_agent.services.code_risk_analysis import dump_code_risk_analysis_run

            return dump_code_risk_analysis_run(run)
        return dump_run(run)
