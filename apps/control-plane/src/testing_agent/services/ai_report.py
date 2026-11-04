from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.encoders import jsonable_encoder

from testing_agent.core.errors import (
    ErrBadRequest,
    ErrNotFound,
    dynamic_error,
)
from testing_agent.core.sid import new_id
from testing_agent.domain.ai_tasks import task_type_for
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.auxiliary_execution import detail_row, lock_or_create_stage
from testing_agent.services.ai_task_access import OwnedRun, RequireProjectAccess
from testing_agent.services.ai_task_output import normalize_config_json
from testing_agent.services.auxiliary_execution import dispatch_auxiliary_execution
from testing_agent.services.auxiliary_execution_view import auxiliary_detail
from testing_agent.services.personal_authorization import require_personal_connection
from testing_agent.services.sprint_daily_metrics import SprintDailyMetricsService
from testing_agent.services.test_report_pdf import markdown_to_pdf_bytes


def build_test_report_run_snapshot(
    task: AiGenerateTask,
    run_id: str,
    snapshot_date: str,
    daily_metrics: dict[str, Any],
    llm_connection_id: str,
    instruction: str | None = None,
) -> dict[str, Any]:
    return {
        "taskId": task.task_id,
        "runId": run_id,
        "taskType": task.task_type,
        "name": task.name,
        "projectId": task.project_id,
        "sprintId": task.sprint_id,
        "requirementId": task.requirement_id,
        "snapshotDate": snapshot_date,
        "llmConnectionId": llm_connection_id,
        "dailyMetrics": jsonable_encoder(daily_metrics),
        "instruction": task.instruction if instruction is None else instruction,
    }


class TestReportWorkflow:
    def __init__(
        self,
        *,
        repository: AiGenerateTaskRepository,
        sprint_daily_metrics_service: SprintDailyMetricsService | None,
        ensure_project_access: RequireProjectAccess,
        owned_run: OwnedRun,
        id_factory: Callable[[], str] = new_id,
    ):
        self.repository = repository
        self.sprint_daily_metrics_service = sprint_daily_metrics_service
        self.ensure_project_access = ensure_project_access
        self.new_id = id_factory

    async def test_report_task_for_run(
        self, project_id: str, body: dict[str, Any], user_id: str
    ) -> AiGenerateTask:
        await self.ensure_project_access(user_id, project_id, action="execute")
        sprint_id = str(body.get("sprintId") or body.get("sprint_id") or "")
        if not sprint_id:
            raise ErrBadRequest()
        # End the authorization snapshot before waiting on the sprint. A new
        # snapshot after its lock sees any task created by the previous holder.
        await self.repository.commit()
        # Parent lock serializes first creation and launch for this iteration.
        sprint = await self.repository.get_sprint_for_update(sprint_id)
        if sprint is None or sprint.project_id != project_id:
            raise ErrNotFound()
        await self.ensure_project_access(user_id, project_id, action="execute")
        existing = await self.repository.get_task_by_project_sprint_type(
            project_id, sprint_id, task_type_for("test_report")
        )
        if existing is not None:
            existing = await self.repository.get_task_for_update(existing.task_id)
            if existing is None:
                raise ErrNotFound()
            return existing
        sprint_name = str(getattr(sprint, "name", "") or "").strip()
        return AiGenerateTask(
            task_id=self.new_id(),
            task_type=task_type_for("test_report"),
            name=f"{sprint_name} 测试报告生成" if sprint_name else "测试报告生成",
            project_id=project_id,
            sprint_id=sprint_id,
            requirement_id="",
            creator_user_id=user_id,
            source_type="daily_metrics",
            source_content="",
            instruction="",
        )

    async def run_test_report(
        self, project_id: str, body: dict[str, Any] | None, user_id: str
    ) -> dict:
        body = body or {}
        llm_connection_id = str(body.get("connectionId") or body.get("llmConnectionId") or "")
        snapshot_date = str(body.get("snapshotDate") or body.get("snapshot_date") or "")
        if not llm_connection_id or not snapshot_date:
            raise ErrBadRequest()
        task = await self.test_report_task_for_run(project_id, body, user_id)
        if getattr(task, "id", None) is None:
            self.repository.add_all([task])
            await self.repository.session.flush()
        await require_personal_connection(
            self.repository.session, user_id, "llm", llm_connection_id, task.project_id
        )
        run_id = self.new_id()
        worker_task_id = self.new_id()
        from testing_agent.services.auxiliary_request import (
            find_replay,
            request_id,
            request_signature,
        )

        dispatch_id = request_id(body.get("requestId"), worker_task_id)
        config = normalize_config_json(body.get("configJson"))
        signature = request_signature(
            "test_report",
            {
                "sprintId": task.sprint_id,
                "snapshotDate": snapshot_date,
                "connectionId": llm_connection_id,
                "instruction": body.get("instruction"),
                "config": config,
                "triggerType": str(body.get("triggerType") or "manual"),
            },
        )
        stage = await lock_or_create_stage(self.repository.session, task.task_id)
        if body.get("requestId") is not None:
            replay = await find_replay(
                self.repository.session,
                task=task,
                actor_id=user_id,
                request_id=dispatch_id,
                signature=signature,
                current_read=True,
                active_attempt_id=stage.active_attempt_id,
            )
            if replay is not None:
                await self.repository.commit()
                if replay.execution_id is None:
                    raise ErrNotFound()
                return await auxiliary_detail(self.repository.session, replay.execution_id)
        if stage.active_attempt_id:
            raise dynamic_error(ErrBadRequest, "测试报告正在生成中，请等待完成后再试")
        if self.sprint_daily_metrics_service is None:
            raise ErrBadRequest()
        daily_metrics = await self.sprint_daily_metrics_service.get(
            task.sprint_id, snapshot_date, user_id
        )
        run_instruction = body.get("instruction")
        snapshot = build_test_report_run_snapshot(
            task,
            run_id,
            snapshot_date,
            daily_metrics,
            llm_connection_id,
            None if run_instruction is None else str(run_instruction),
        )
        attempt, _ = await dispatch_auxiliary_execution(
            self.repository.session,
            task=task,
            actor_id=user_id,
            request_id=dispatch_id,
            execution_id=run_id,
            connection_id=llm_connection_id,
            source=snapshot,
            config=config,
            trigger_type=str(body.get("triggerType") or "manual"),
            request_signature=signature,
        )
        await self.repository.commit()
        return await auxiliary_detail(self.repository.session, attempt.execution_id or run_id)

    async def export_test_report_pdf(self, run_id: str, user_id: str) -> tuple[bytes, str]:
        row = await detail_row(self.repository.session, run_id)
        if row is None:
            raise ErrNotFound()
        _, task, _ = row
        if task.task_type != task_type_for("test_report"):
            raise ErrNotFound()
        await self.ensure_project_access(user_id, task.project_id, action="read")
        sprint = await self.repository.get_sprint(task.sprint_id)
        if sprint is None or sprint.project_id != task.project_id:
            raise ErrNotFound()
        payload = await auxiliary_detail(self.repository.session, run_id)
        markdown = str(payload.get("resultYaml") or "").strip()
        if not markdown:
            raise ErrBadRequest()
        snapshot = payload.get("snapshotJson") or {}
        title = str(snapshot.get("name") or "测试报告")
        return markdown_to_pdf_bytes(markdown, title=title), f"test-report-{run_id}.pdf"
