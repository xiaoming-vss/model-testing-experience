"""Launch AI runs with preparation and final authorization in separate transactions.

The final transaction owns run, stages, attempt and dispatch together. Remote
snapshot preparation finishes before current permissions and parent scope are
rechecked under locks.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from testing_agent.core.errors import (
    ErrBadRequest,
    ErrNotFound,
    dynamic_error,
)
from testing_agent.core.sid import new_id
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.ai_generate_task_source_archive import (
    AiGenerateTaskSourceArchiveRepository,
)
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
        execution: object | None = None,
        sprint_daily_metrics_service: SprintDailyMetricsService | None = None,
        code_risk_analysis_service: CodeRiskAnalysisService | None = None,
        id_factory: Callable[[], str] = new_id,
    ) -> None:
        self.repository = repository
        self.source_archive_repository = source_archive_repository
        self.access = access
        self.sprint_daily_metrics_service = sprint_daily_metrics_service
        self.code_risk_analysis_service = code_risk_analysis_service
        self.id_factory = id_factory

    async def launch(
        self,
        kind: str,
        task_id: str,
        body: dict[str, Any] | None,
        user_id: str,
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
        if kind == "requirement_analysis" or (
            kind in {"function", "api", "ui"} and task.requirement_id
        ):
            raise dynamic_error(ErrBadRequest, "请在需求生成链中启动独立阶段")
        if kind == "ui":
            raise dynamic_error(ErrBadRequest, "请先为 UI 任务关联需求，再使用需求生成链")
        if kind not in {"function", "api", "code_risk_analysis"}:
            raise ErrBadRequest()
        task_scope = (task.project_id, task.sprint_id, task.requirement_id)
        body = body or {}
        llm_connection_id = str(body.get("connectionId") or body.get("llmConnectionId") or "")
        if not llm_connection_id:
            raise ErrBadRequest()
        await require_personal_connection(
            self.repository.session, user_id, "llm", llm_connection_id, task.project_id
        )
        run_id = self.id_factory()
        worker_task_id = self.id_factory()
        run_instruction = body.get("instruction")
        config = normalize_config_json(body.get("configJson")) or {}
        trigger_type = str(body.get("triggerType") or "manual")
        risk_request_id = worker_task_id
        risk_signature = ""
        if kind == "code_risk_analysis":
            from testing_agent.services.auxiliary_execution_view import auxiliary_detail
            from testing_agent.services.auxiliary_request import (
                find_replay,
                request_signature,
            )
            from testing_agent.services.auxiliary_request import (
                request_id as normalize_request_id,
            )

            risk_request_id = normalize_request_id(body.get("requestId"), worker_task_id)
            risk_signature = request_signature(
                kind,
                {
                    "connectionId": llm_connection_id,
                    "gitlabConnectionIds": body.get("gitlabConnectionIds") or {},
                    "instruction": run_instruction,
                    "config": config,
                    "triggerType": trigger_type,
                    "requirementUnderstandingVersionId": str(
                        body.get("requirementUnderstandingVersionId") or ""
                    ),
                },
            )
            if body.get("requestId") is not None:
                replay = await find_replay(
                    self.repository.session,
                    task=task,
                    actor_id=user_id,
                    request_id=risk_request_id,
                    signature=risk_signature,
                )
                if replay is not None:
                    if not replay.execution_id:
                        raise ErrNotFound()
                    return await auxiliary_detail(self.repository.session, replay.execution_id)
            if self.code_risk_analysis_service is None:
                raise ErrBadRequest()
            await self.repository.commit()
            snapshot = await self.code_risk_analysis_service.build_snapshot(
                task,
                run_id,
                risk_request_id,
                None if run_instruction is None else str(run_instruction),
                user_id=user_id,
                connection_ids=body.get("gitlabConnectionIds") or {},
                understanding_version_id=str(body.get("requirementUnderstandingVersionId") or ""),
            )
        else:
            snapshot = await build_generate_run_snapshot(
                self.repository,
                kind,
                task,
                run_id,
                None if run_instruction is None else str(run_instruction),
                worker_task_id=worker_task_id,
                understanding_version_id=str(body.get("requirementUnderstandingVersionId") or ""),
            )
        if kind == "api" and body.get("apiWorkflowVersion") == "api_two_stage/1.0":
            snapshot["apiWorkflowVersion"] = "api_two_stage/1.0"
        # End the preparation snapshot before rechecking permissions. Under
        # REPEATABLE READ, a normal membership/connection read would otherwise
        # keep seeing credentials or roles revoked during a remote request.
        await self.repository.commit()
        api_two_stage = kind == "api" and snapshot.get("apiWorkflowVersion") == "api_two_stage/1.0"
        if api_two_stage and body.get("checkpointEnabled") is False:
            raise dynamic_error(ErrBadRequest, "API 两阶段生成需要人工审核")
        checkpoint_enabled = True if api_two_stage else bool(body.get("checkpointEnabled", False))
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
        if (
            current_task.project_id,
            current_task.sprint_id,
            current_task.requirement_id,
        ) != task_scope:
            raise ErrBadRequest()
        await require_personal_connection(
            self.repository.session, user_id, "llm", llm_connection_id, task.project_id
        )
        await self.access.validate_task_scope(current_task)
        if kind == "code_risk_analysis":
            from testing_agent.repositories.auxiliary_execution import lock_or_create_stage
            from testing_agent.services.auxiliary_execution import dispatch_auxiliary_execution
            from testing_agent.services.auxiliary_execution_view import auxiliary_detail

            stage = await lock_or_create_stage(self.repository.session, current_task.task_id)
            if body.get("requestId") is not None:
                replay = await find_replay(
                    self.repository.session,
                    task=current_task,
                    actor_id=user_id,
                    request_id=risk_request_id,
                    signature=risk_signature,
                    current_read=True,
                    active_attempt_id=stage.active_attempt_id,
                )
                if replay is not None:
                    if not replay.execution_id:
                        raise ErrNotFound()
                    await self.repository.commit()
                    return await auxiliary_detail(self.repository.session, replay.execution_id)
            if stage.active_attempt_id:
                raise dynamic_error(ErrBadRequest, "代码风险正在生成中，请等待完成后再试")
            attempt, _ = await dispatch_auxiliary_execution(
                self.repository.session,
                task=current_task,
                actor_id=user_id,
                request_id=risk_request_id,
                execution_id=run_id,
                connection_id=llm_connection_id,
                source=snapshot,
                config=config,
                trigger_type=trigger_type,
                request_signature=risk_signature,
            )
            await self.repository.commit()
            return await auxiliary_detail(self.repository.session, attempt.execution_id or run_id)
        # Independent functional and API workflows use execution IDs.
        from testing_agent.services.standalone_execution import start_standalone_execution
        from testing_agent.services.standalone_execution_view import project_standalone_execution

        supplied_request = body.get("requestId")
        if supplied_request is not None and (
            not isinstance(supplied_request, str)
            or not supplied_request.strip()
            or len(supplied_request.strip()) > 64
        ):
            raise ErrBadRequest()
        request_id = (
            supplied_request.strip() if isinstance(supplied_request, str) else worker_task_id
        )
        execution, _, _ = await start_standalone_execution(
            self.repository.session,
            task=current_task,
            execution_id=run_id,
            request_id=request_id,
            actor_id=user_id,
            connection_id=llm_connection_id,
            source=snapshot,
            config=config,
            checkpoint_enabled=checkpoint_enabled,
            trigger_type=trigger_type,
        )
        await self.repository.commit()
        return dump_run(
            await project_standalone_execution(self.repository.session, execution.execution_id)
        )
