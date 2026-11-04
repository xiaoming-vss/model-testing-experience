from __future__ import annotations

from typing import Any

from testing_agent.core.errors import (
    ErrBadRequest,
    ErrNotFound,
)
from testing_agent.domain.ai_tasks import (
    task_type_for,
)
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
        archives = (
            await self.source_archive_repository.list_source_archives([row.task_id for row in rows])
            if kind == "ui"
            else {}
        )
        payloads = []
        for row in rows:
            await self.access.validate_task_scope(row, scopes)
            payloads.append(dump_task(row, archives.get(row.task_id)))
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
        task = await self.access.owned_task(user_id, task_id, kind, action="read")
        if kind == "requirement_analysis" or (
            kind in {"function", "api", "ui"} and task.requirement_id
        ):
            from testing_agent.services.stage_storage.history_view import direct_history

            return await direct_history(
                self.repository.session, task_id, page, page_size, pipeline_filter
            )
        if kind in {"function", "api", "ui"} and not task.requirement_id:
            from testing_agent.services.standalone_history import standalone_history

            return await standalone_history(
                self.repository.session, task_id, page, page_size, pipeline_filter
            )
        if kind == "code_risk_analysis" and pipeline_filter == "all":
            from testing_agent.services.auxiliary_execution_view import auxiliary_history

            return await auxiliary_history(self.repository.session, task_id, page, page_size)
        raise ErrBadRequest()

    async def list_test_report_run_summaries(
        self, project_id: str, sprint_id: str, user_id: str, page: int = 1, page_size: int = 20
    ) -> dict[str, Any]:
        from testing_agent.core.errors import ErrBadRequest
        from testing_agent.services.auxiliary_execution_view import auxiliary_history

        await self.access.ensure_project_access(user_id, project_id, action="read")
        sprint = await self.repository.get_sprint(sprint_id)
        if sprint is None or sprint.project_id != project_id:
            raise ErrNotFound()
        task = await self.repository.get_task_by_project_sprint_type(
            project_id, sprint_id, task_type_for("test_report")
        )
        if task is not None:
            return await auxiliary_history(self.repository.session, task.task_id, page, page_size)
        if page < 1 or not 1 <= page_size <= 100:
            raise ErrBadRequest()
        return {
            "items": [],
            "total": 0,
            "statusCounts": {},
            "reviewPendingCount": 0,
            "latestRun": None,
        }

    async def get_run(self, kind: str, run_id: str, user_id: str) -> dict[str, Any]:
        if kind == "function":
            from testing_agent.services.stage_storage.relations import find_leaf, graph_view

            session = self.repository.session
            found = await find_leaf(session, run_id)
            if found is not None:
                leaf, task = found
                await self.access.owned_task(user_id, task.task_id, "function", action="read")
                return await graph_view(session, task, leaf)
        if kind in {"requirement_analysis", "function", "api", "ui"}:
            from testing_agent.repositories.direct_attempt_view import direct_attempt_task_id
            from testing_agent.services.stage_storage.run_view import direct_attempt_view

            session = self.repository.session
            task_id = await direct_attempt_task_id(session, run_id)
            if task_id is not None:
                await self.access.owned_task(user_id, task_id, kind, action="read")
                return await direct_attempt_view(session, task_id, run_id)
        if kind in {"function", "api", "ui"}:
            from testing_agent.repositories.standalone_execution import workflow_task_id
            from testing_agent.services.standalone_execution_view import (
                project_standalone_execution,
            )

            session = self.repository.session
            task_id = await workflow_task_id(session, run_id)
            if task_id is not None:
                await self.access.owned_task(user_id, task_id, kind, action="read")
                return dump_run(await project_standalone_execution(session, run_id))
            raise ErrNotFound()
        if kind in {"code_risk_analysis", "test_report", "test_order_graph"}:
            from testing_agent.repositories.auxiliary_execution import detail_row
            from testing_agent.services.auxiliary_execution_view import auxiliary_detail

            row = await detail_row(self.repository.session, run_id)
            if row is not None:
                _, task, _ = row
                await self.access.owned_task(user_id, task.task_id, kind, action="read")
                return await auxiliary_detail(self.repository.session, run_id)
            raise ErrNotFound()
        raise ErrNotFound()
