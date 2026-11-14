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
from testing_agent.services.ai_task_output import (
    dump_run,
    dump_task,
    dump_task_summary,
)
from testing_agent.services.ai_task_scope import GenerationAccess
from testing_agent.services.common import list_payload

# The Studio's AI task list uses these buckets; raw statuses stay in statusCounts.
_CODE_RISK_STATUS_BUCKETS: dict[str, tuple[str, ...]] = {
    "in_progress": ("pending", "queued", "claimed", "running"),
    "success": ("success",),
    "waiting_review": ("waiting_review",),
    "failed": ("failed", "error"),
}


class GenerationQueries:
    """Task/detail/history reads through current resource authorization."""

    def __init__(
        self,
        repository: AiGenerateTaskRepository,
        access: GenerationAccess,
    ) -> None:
        self.repository = repository
        self.access = access

    async def list(
        self,
        kind: str,
        project_id: str,
        user_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        sprint_id: str = "",
        requirement_id: str = "",
        keyword: str = "",
        status: str = "",
    ) -> dict[str, Any]:
        if page < 1 or not 1 <= page_size <= 100:
            raise ErrBadRequest()
        status = status.strip()
        if status and kind != "code_risk_analysis":
            raise ErrBadRequest()
        status_values = _CODE_RISK_STATUS_BUCKETS.get(status) if status else None
        if status and status_values is None:
            raise ErrBadRequest()

        await self.access.ensure_project_access(user_id, project_id, action="read")
        task_type = task_type_for(kind)
        total = await self.repository.count_tasks(
            project_id,
            task_type,
            sprint_id=sprint_id,
            requirement_id=requirement_id,
            keyword=keyword,
            status_values=status_values,
        )
        rows = await self.repository.list_tasks_page(
            project_id,
            task_type,
            sprint_id=sprint_id,
            requirement_id=requirement_id,
            keyword=keyword,
            status_values=status_values,
            page=page,
            page_size=page_size,
        )
        scope_loader = getattr(self.repository, "task_scope_resources", None)
        scopes = (
            await scope_loader([task for task, _ in rows]) if scope_loader is not None else None
        )
        payloads = []
        for task, latest_run_status in rows:
            await self.access.validate_task_scope(task, scopes)
            payloads.append(dump_task_summary(task, latest_run_status))
        status_counts = (
            await self.repository.task_status_counts(
                project_id,
                task_type,
                sprint_id=sprint_id,
                requirement_id=requirement_id,
                keyword=keyword,
            )
            if kind == "code_risk_analysis"
            else {}
        )
        return {"items": payloads, "total": total, "statusCounts": status_counts}

    async def get(self, kind: str, task_id: str, user_id: str) -> dict:
        task = await self.access.owned_task(user_id, task_id, kind, action="read")
        return dump_task(task)

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
        if kind in {"code_risk_analysis", "repository_profile"} and pipeline_filter == "all":
            from testing_agent.services.auxiliary_execution_view import auxiliary_history

            return await auxiliary_history(self.repository.session, task_id, page, page_size)
        raise ErrBadRequest()

    async def list_profile_versions(self, task_id: str, user_id: str) -> dict[str, Any]:
        task = await self.access.owned_task(user_id, task_id, "repository_profile", action="read")
        from testing_agent.services.repository_profile_versions import list_profile_versions

        return list_payload(await list_profile_versions(self.repository.session, task.task_id))

    async def list_project_latest_runs(
        self, kind: str, project_id: str, user_id: str
    ) -> dict[str, Any]:
        """Latest run summary for every auxiliary task in a project.

        The Studio used to issue one runs request per task to fill its list; this
        read keeps the same summary shape but returns the project in one request.
        """
        if kind != "code_risk_analysis":
            raise ErrBadRequest()
        await self.access.ensure_project_access(user_id, project_id, action="read")
        from testing_agent.services.auxiliary_execution_view import (
            latest_project_run_summaries,
        )

        return list_payload(
            await latest_project_run_summaries(
                self.repository.session, project_id, "code_risk_analysis"
            )
        )

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
        if kind in {
            "code_risk_analysis",
            "repository_profile",
            "test_report",
            "test_order_graph",
        }:
            from testing_agent.repositories.auxiliary_execution import detail_row
            from testing_agent.services.auxiliary_execution_view import auxiliary_detail

            row = await detail_row(self.repository.session, run_id)
            if row is not None:
                _, task, _ = row
                await self.access.owned_task(user_id, task.task_id, kind, action="read")
                return await auxiliary_detail(self.repository.session, run_id)
            raise ErrNotFound()
        raise ErrNotFound()
