from __future__ import annotations

import builtins
from collections.abc import Callable
from typing import Any

from fastapi.encoders import jsonable_encoder

from testing_agent.core.enums import RunStatus
from testing_agent.core.errors import (
    ErrBadRequest,
    ErrNotFound,
)
from testing_agent.core.sid import new_id
from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.ai_task_access import OwnedRun, RequireProjectAccess
from testing_agent.services.ai_task_contracts import task_type_for
from testing_agent.services.ai_task_output import dump_run, normalize_config_json
from testing_agent.services.common import list_payload
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
        self.owned_run = owned_run
        self.new_id = id_factory

    async def test_report_task_for_run(
        self, project_id: str, body: dict[str, Any], user_id: str
    ) -> AiGenerateTask:
        await self.ensure_project_access(user_id, project_id, action="execute")
        sprint_id = str(body.get("sprintId") or body.get("sprint_id") or "")
        if not sprint_id:
            raise ErrBadRequest
        sprint = await self.repository.get_sprint(sprint_id)
        if sprint is None or sprint.project_id != project_id:
            raise ErrNotFound
        existing = await self.repository.get_active_task_by_project_sprint_type(
            project_id, sprint_id, task_type_for("test_report")
        )
        if existing is not None:
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
            raise ErrBadRequest
        task = await self.test_report_task_for_run(project_id, body, user_id)
        await require_personal_connection(
            self.repository.session, user_id, "llm", llm_connection_id, task.project_id
        )
        run_id = self.new_id()
        worker_task_id = self.new_id()
        if self.sprint_daily_metrics_service is None:
            raise ErrBadRequest
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
        run = AiGenerateTaskRun(
            run_id=run_id,
            task_id=task.task_id,
            requirement_id="",
            sprint_id=task.sprint_id,
            project_id=task.project_id,
            trigger_user_id=user_id,
            trigger_type=str(body.get("triggerType") or "manual"),
            status=RunStatus.PENDING.value,
            checkpoint_enabled=False,
            current_stage="",
            stage_status="",
            snapshot_json=snapshot,
            config_json=normalize_config_json(body.get("configJson")),
            result_summary_json={},
        )
        worker_task = WorkerTask(
            domain="ai",
            task_id=worker_task_id,
            task_type=task.task_type,
            run_id=run.run_id,
            generate_task_id=task.task_id,
            llm_connection_id=llm_connection_id,
            status=RunStatus.PENDING.value,
        )
        rows: builtins.list[object] = [run, worker_task]
        if getattr(task, "id", None) is None:
            rows.insert(0, task)
        self.repository.add_all(rows)
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def list_test_report_runs(
        self, project_id: str, sprint_id: str, user_id: str
    ) -> dict[str, Any]:
        await self.ensure_project_access(user_id, project_id, action="read")
        sprint = await self.repository.get_sprint(sprint_id)
        if sprint is None or sprint.project_id != project_id:
            raise ErrNotFound
        rows = await self.repository.list_runs_by_project_sprint_task_type(
            project_id, sprint_id, task_type_for("test_report")
        )
        return list_payload([dump_run(row) for row in rows])

    async def export_test_report_pdf(self, run_id: str, user_id: str) -> tuple[bytes, str]:
        run = await self.owned_run(user_id, run_id, "test_report", action="read")
        markdown = str(run.result_yaml or "").strip()
        if not markdown:
            raise ErrBadRequest
        snapshot = run.snapshot_json if isinstance(run.snapshot_json, dict) else {}
        title = str(snapshot.get("name") or "测试报告")
        filename = f"test-report-{run.run_id}.pdf"
        return markdown_to_pdf_bytes(markdown, title=title), filename
