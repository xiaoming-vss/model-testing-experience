"""Launch AI runs with preparation and final authorization in separate transactions.

The final transaction owns run, stages, attempt and dispatch together. Remote
snapshot preparation finishes before current permissions and parent scope are
rechecked under locks; response-loss retries keep the original request identity.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from testing_agent.core.enums import RunStatus, StageStatus
from testing_agent.core.errors import ErrAiGenerateTaskRunRunning, ErrBadRequest, ErrNotFound
from testing_agent.core.sid import new_id
from testing_agent.domain.ai_execution_intent import ExecutionIntent
from testing_agent.domain.ai_tasks import REQUIREMENT_ANALYSIS_INITIAL_STAGE
from testing_agent.models.ai_generate_task import AiGenerateTaskRun
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.ai_generate_task_source_archive import (
    AiGenerateTaskSourceArchiveRepository,
)
from testing_agent.services.ai_execution.writer import ExecutionWriter
from testing_agent.services.ai_report import build_test_report_run_snapshot
from testing_agent.services.ai_task_access import RunLaunchAccess
from testing_agent.services.ai_task_output import (
    build_generate_run_snapshot,
    dump_run,
    normalize_config_json,
)
from testing_agent.services.personal_authorization import require_personal_connection
from testing_agent.services.project_access import require_project_access
from testing_agent.services.sprint_daily_metrics import SprintDailyMetricsService

if TYPE_CHECKING:
    from testing_agent.services.code_risk_analysis import CodeRiskAnalysisService


class GenerationRunLauncher:
    def __init__(
        self,
        *,
        repository: AiGenerateTaskRepository,
        source_archive_repository: AiGenerateTaskSourceArchiveRepository,
        access: RunLaunchAccess,
        execution: ExecutionWriter,
        sprint_daily_metrics_service: SprintDailyMetricsService | None = None,
        code_risk_analysis_service: CodeRiskAnalysisService | None = None,
        id_factory: Callable[[], str] = new_id,
    ) -> None:
        self.repository = repository
        self.source_archive_repository = source_archive_repository
        self.access = access
        self.execution = execution
        self.sprint_daily_metrics_service = sprint_daily_metrics_service
        self.code_risk_analysis_service = code_risk_analysis_service
        self.id_factory = id_factory

    async def launch(
        self,
        kind: str,
        task_id: str,
        body: dict[str, Any] | None,
        user_id: str,
        *,
        request_id: str | None = None,
    ) -> dict:
        task = await self.access.owned_task(user_id, task_id, kind, action="read")
        # Remote snapshot preparation must not hold project/run locks.
        project = await self.repository.get_project(task.project_id)
        if project is None:
            raise ErrNotFound()
        await require_project_access(
            self.repository.session,
            user_id,
            project,
            "execute",
        )
        body = body or {}
        if kind == "requirement_analysis":
            requirement = await self.repository.get_requirement(task.requirement_id)
            if requirement is None:
                raise ErrNotFound()
            if not str(getattr(requirement, "document_file_id", "") or "").strip():
                from testing_agent.core.errors import ErrRequirementFileMissing

                raise ErrRequirementFileMissing()
        source_archive_file_id = ""
        if kind == "ui":
            archive = await self.source_archive_repository.get_source_archive(task.task_id)
            if archive is None:
                raise ErrBadRequest()
            source_archive_file_id = getattr(archive, "file_id", "") or ""
            if not source_archive_file_id:
                from testing_agent.core.errors import AppError

                raise AppError(409, "源码包未存储到 S3，请重新上传", 409)
        llm_connection_id = str(body.get("connectionId") or body.get("llmConnectionId") or "")
        if not llm_connection_id:
            raise ErrBadRequest()
        await require_personal_connection(
            self.repository.session, user_id, "llm", llm_connection_id, task.project_id
        )
        if request_id:
            existing = await self.repository.get_run(request_id)
            if existing is not None:
                if existing.task_id != task_id or existing.trigger_user_id != user_id:
                    raise ErrBadRequest()
                return dump_run(existing)
        run_id = request_id or self.id_factory()
        worker_task_id = self.id_factory()
        run_instruction = body.get("instruction")
        if kind == "test_report":
            snapshot_date = str(body.get("snapshotDate") or body.get("snapshot_date") or "")
            if not snapshot_date:
                raise ErrBadRequest()
            if self.sprint_daily_metrics_service is None:
                raise ErrBadRequest()
            daily_metrics = await self.sprint_daily_metrics_service.get(
                task.sprint_id, snapshot_date, user_id
            )
            snapshot = build_test_report_run_snapshot(
                task,
                run_id,
                snapshot_date,
                daily_metrics,
                llm_connection_id,
                None if run_instruction is None else str(run_instruction),
            )
        elif kind == "code_risk_analysis":
            if self.code_risk_analysis_service is None:
                raise ErrBadRequest()
            await self.repository.commit()
            snapshot = await self.code_risk_analysis_service.build_snapshot(
                task,
                run_id,
                worker_task_id,
                None if run_instruction is None else str(run_instruction),
                user_id=user_id,
                connection_ids=body.get("gitlabConnectionIds") or {},
            )
        else:
            snapshot = await build_generate_run_snapshot(
                self.repository,
                kind,
                task,
                run_id,
                None if run_instruction is None else str(run_instruction),
                worker_task_id=worker_task_id,
            )
        if kind == "ui":
            snapshot["sourceArchiveFileId"] = source_archive_file_id
        if kind == "requirement_analysis":
            snapshot["workflowVersion"] = 2
            snapshot["sourceContent"] = snapshot.get("documentDownloadUrl", "")
        # End the preparation snapshot before rechecking permissions. Under
        # REPEATABLE READ, a normal membership/connection read would otherwise
        # keep seeing credentials or roles revoked during a remote request.
        await self.repository.commit()
        checkpoint_enabled = (
            True if kind == "requirement_analysis" else bool(body.get("checkpointEnabled", False))
        )
        current_stage = ""
        if checkpoint_enabled:
            if kind == "function":
                current_stage = "requirement_analysis"
            elif kind == "requirement_analysis":
                current_stage = REQUIREMENT_ANALYSIS_INITIAL_STAGE
        stage_status = StageStatus.PENDING.value if current_stage else ""
        run = AiGenerateTaskRun(
            run_id=run_id,
            task_id=task.task_id,
            requirement_id=task.requirement_id,
            sprint_id=task.sprint_id,
            project_id=task.project_id,
            trigger_user_id=user_id,
            trigger_type=str(body.get("triggerType") or "manual"),
            status=RunStatus.PENDING.value,
            checkpoint_enabled=checkpoint_enabled,
            current_stage=current_stage,
            stage_status=stage_status,
            snapshot_json=snapshot,
            config_json=normalize_config_json(body.get("configJson")),
            result_summary_json={},
        )
        worker_task = WorkerTask(
            domain="ai",
            task_id=worker_task_id,
            task_type=task.task_type,
            run_id=run.run_id,
            status=RunStatus.PENDING.value,
        )
        # Lock and revalidate immediately before inserting the child records.
        await self.access.ensure_project_access(user_id, task.project_id, action="execute")
        if task.sprint_id:
            await self.access.ensure_sprint_access(user_id, task.sprint_id, action="execute")
        if task.requirement_id:
            await self.access.ensure_requirement_access(
                user_id, task.requirement_id, action="execute"
            )
        current_task = await getattr(
            self.repository, "get_task_for_update", self.repository.get_task
        )(task.task_id)
        if current_task is None:
            raise ErrNotFound()
        if (current_task.project_id, current_task.sprint_id, current_task.requirement_id) != (
            run.project_id,
            run.sprint_id,
            run.requirement_id,
        ):
            raise ErrBadRequest()
        await require_personal_connection(
            self.repository.session, user_id, "llm", llm_connection_id, task.project_id
        )
        await self.access.validate_task_scope(current_task)
        if request_id:
            # Task lock serializes same-request inserts. The unique run_id remains
            # the database backstop. A response-loss retry returns the same run.
            existing = await self.repository.get_run_for_update(request_id)
            if existing is not None:
                if existing.task_id != task_id or existing.trigger_user_id != user_id:
                    raise ErrBadRequest()
                return dump_run(existing)
            if await self.repository.has_active_run(task_id):
                raise ErrAiGenerateTaskRunRunning()
        self.repository.add_all([run, worker_task])
        await self.execution.save(
            self.repository.session,
            run,
            intent=ExecutionIntent(actor_id=user_id, llm_connection_id=llm_connection_id),
            worker=worker_task,
        )
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)
