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
from testing_agent.domain.generation_root_fingerprints import IncompleteRootInput
from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.generation_chain import GenerationChainRepository
from testing_agent.services.ai_task_access import RunLaunchAccess
from testing_agent.services.ai_task_output import (
    build_generate_run_snapshot,
    dump_run,
    normalize_config_json,
)
from testing_agent.services.generation_current_material import (
    CurrentMaterial,
    lock_current_material,
)
from testing_agent.services.generation_document_preparation import (
    PreparedRequirementDocument,
    lock_prepared_requirement_root,
    prepare_requirement_document,
)
from testing_agent.services.generation_source_errors import closure_error, source_error
from testing_agent.services.personal_authorization import require_personal_connection
from testing_agent.services.project_access import require_project_access
from testing_agent.services.sprint_daily_metrics import SprintDailyMetricsService

if TYPE_CHECKING:
    from testing_agent.services.code_risk_analysis import CodeRiskAnalysisService
    from testing_agent.services.repository_profile import RepositoryProfileService
    from testing_agent.services.stored_file import StoredFileService


class GenerationRunLauncher:
    def __init__(
        self,
        *,
        repository: AiGenerateTaskRepository,
        access: RunLaunchAccess,
        execution: object | None = None,
        sprint_daily_metrics_service: SprintDailyMetricsService | None = None,
        code_risk_analysis_service: CodeRiskAnalysisService | None = None,
        repository_profile_service: RepositoryProfileService | None = None,
        files: StoredFileService | None = None,
        id_factory: Callable[[], str] = new_id,
    ) -> None:
        self.repository = repository
        self.access = access
        self.sprint_daily_metrics_service = sprint_daily_metrics_service
        self.code_risk_analysis_service = code_risk_analysis_service
        self.repository_profile_service = repository_profile_service
        self.files = files
        self.id_factory = id_factory

    async def _prepare_current_material(
        self, *, task: AiGenerateTask, bound_task_id: str, actor_id: str
    ) -> tuple[PreparedRequirementDocument, CurrentMaterial]:
        """Prepare outside locks, then inspect the current material under locks."""
        if self.files is None:
            raise dynamic_error(ErrBadRequest, "需求文件存储不可用")
        try:
            document = await prepare_requirement_document(
                self.repository.session, requirement_id=task.requirement_id, files=self.files
            )
            await self.repository.commit()
            await self.access.ensure_project_access(actor_id, task.project_id, action="execute")
            if task.sprint_id:
                await self.access.ensure_sprint_access(actor_id, task.sprint_id, action="execute")
            await self.access.ensure_requirement_access(
                actor_id, task.requirement_id, action="execute"
            )
            chain = GenerationChainRepository(self.repository.session)
            if (
                await chain.candidate_chain_task(task.requirement_id, "requirement_analysis")
                != bound_task_id
            ):
                raise SourceClosureError("concurrent_change")
            bound = await self.repository.get_task_for_update(bound_task_id)
            if bound is None or bound.requirement_id != task.requirement_id:
                raise SourceClosureError("source_unknown")
            await self.access.validate_task_scope(bound)
            root = await lock_prepared_requirement_root(self.repository.session, prepared=document)
            material = await lock_current_material(
                self.repository.session,
                requirement_id=task.requirement_id,
                document_root=root,
                freeze=False,
            )
            await self.repository.commit()
            return document, material
        except IncompleteRootInput as exc:
            await self.repository.session.rollback()
            raise source_error("source_unknown") from exc
        except SourceClosureError as exc:
            await self.repository.session.rollback()
            raise closure_error(exc) from exc
        except Exception:
            await self.repository.session.rollback()
            raise

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
        if kind not in {"function", "api", "code_risk_analysis", "repository_profile"}:
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
        auxiliary_request_id = worker_task_id
        auxiliary_signature = ""
        candidate_material_task_id: str | None = None
        prepared_document: PreparedRequirementDocument | None = None
        current_material: CurrentMaterial | None = None
        if kind in {"code_risk_analysis", "repository_profile"}:
            from testing_agent.services.auxiliary_execution_view import auxiliary_detail
            from testing_agent.services.auxiliary_request import (
                find_replay,
                request_signature,
            )
            from testing_agent.services.auxiliary_request import (
                request_id as normalize_request_id,
            )

            auxiliary_request_id = normalize_request_id(body.get("requestId"), worker_task_id)
            auxiliary_signature = request_signature(
                kind,
                {
                    "connectionId": llm_connection_id,
                    "gitlabConnectionIds": body.get("gitlabConnectionIds") or {},
                    "instruction": run_instruction,
                    "config": config,
                    "triggerType": trigger_type,
                },
            )
            if body.get("requestId") is not None:
                replay = await find_replay(
                    self.repository.session,
                    task=task,
                    actor_id=user_id,
                    request_id=auxiliary_request_id,
                    signature=auxiliary_signature,
                )
                if replay is not None:
                    if not replay.execution_id:
                        raise ErrNotFound()
                    return await auxiliary_detail(self.repository.session, replay.execution_id)
            await self.repository.commit()
            if task.requirement_id:
                candidate_material_task_id = await GenerationChainRepository(
                    self.repository.session
                ).candidate_chain_task(task.requirement_id, "requirement_analysis")
                await self.repository.commit()
            if not candidate_material_task_id:
                raise dynamic_error(ErrBadRequest, "请先采用当前材料整理结果")
            prepared_document, current_material = await self._prepare_current_material(
                task=task, bound_task_id=candidate_material_task_id, actor_id=user_id
            )
            if kind == "code_risk_analysis":
                if self.code_risk_analysis_service is None:
                    raise ErrBadRequest()
                snapshot = await self.code_risk_analysis_service.build_snapshot(
                    task,
                    run_id,
                    auxiliary_request_id,
                    None if run_instruction is None else str(run_instruction),
                    user_id=user_id,
                    connection_ids=body.get("gitlabConnectionIds") or {},
                    current_material=current_material,
                )
            else:
                if self.repository_profile_service is None:
                    raise ErrBadRequest()
                snapshot = await self.repository_profile_service.build_snapshot(
                    task,
                    run_id,
                    auxiliary_request_id,
                    None if run_instruction is None else str(run_instruction),
                    user_id=user_id,
                    connection_ids=body.get("gitlabConnectionIds") or {},
                    current_material=current_material,
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
        if kind == "api" and body.get("apiWorkflowVersion") == "api_three_stage/1.0":
            snapshot["apiWorkflowVersion"] = "api_three_stage/1.0"
        # End the preparation snapshot before rechecking permissions. Under
        # REPEATABLE READ, a normal membership/connection read would otherwise
        # keep seeing credentials or roles revoked during a remote request.
        await self.repository.commit()
        api_three_stage = (
            kind == "api" and snapshot.get("apiWorkflowVersion") == "api_three_stage/1.0"
        )
        if api_three_stage and body.get("checkpointEnabled") is False:
            raise dynamic_error(ErrBadRequest, "API 三阶段生成需要人工审核")
        checkpoint_enabled = True if api_three_stage else bool(body.get("checkpointEnabled", False))
        # Lock and revalidate immediately before inserting the child records.
        await self.access.ensure_project_access(user_id, task.project_id, action="execute")
        if task.sprint_id:
            await self.access.ensure_sprint_access(user_id, task.sprint_id, action="execute")
        if task.requirement_id:
            await self.access.ensure_requirement_access(
                user_id, task.requirement_id, action="execute"
            )
        if kind in {"code_risk_analysis", "repository_profile"} and task.requirement_id:
            final_bound_task_id = await GenerationChainRepository(
                self.repository.session
            ).candidate_chain_task(task.requirement_id, "requirement_analysis")
            if final_bound_task_id != candidate_material_task_id:
                raise dynamic_error(ErrBadRequest, "材料生成链已变化，请重新发起分析")
            if final_bound_task_id:
                bound = await self.repository.get_task_for_update(final_bound_task_id)
                if bound is None or bound.requirement_id != task.requirement_id:
                    raise ErrNotFound()
                await self.access.validate_task_scope(bound)
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
        if kind in {"code_risk_analysis", "repository_profile"}:
            from testing_agent.repositories.auxiliary_execution import lock_or_create_stage
            from testing_agent.services.auxiliary_execution import dispatch_auxiliary_execution
            from testing_agent.services.auxiliary_execution_view import auxiliary_detail

            if current_material is not None:
                assert prepared_document is not None
                try:
                    root = await lock_prepared_requirement_root(
                        self.repository.session, prepared=prepared_document
                    )
                    await lock_current_material(
                        self.repository.session,
                        requirement_id=task.requirement_id,
                        document_root=root,
                        freeze=True,
                        expected=current_material,
                    )
                except IncompleteRootInput as exc:
                    raise source_error("source_unknown") from exc
                except SourceClosureError as exc:
                    raise closure_error(exc) from exc
            else:
                raise dynamic_error(ErrBadRequest, "请先采用当前材料整理结果")
            stage = await lock_or_create_stage(self.repository.session, current_task.task_id)
            if body.get("requestId") is not None:
                replay = await find_replay(
                    self.repository.session,
                    task=current_task,
                    actor_id=user_id,
                    request_id=auxiliary_request_id,
                    signature=auxiliary_signature,
                    current_read=True,
                    active_attempt_id=stage.active_attempt_id,
                )
                if replay is not None:
                    if not replay.execution_id:
                        raise ErrNotFound()
                    await self.repository.commit()
                    return await auxiliary_detail(self.repository.session, replay.execution_id)
            if stage.active_attempt_id:
                running_message = (
                    "仓库画像正在生成中，请等待完成后再试"
                    if kind == "repository_profile"
                    else "代码风险正在生成中，请等待完成后再试"
                )
                raise dynamic_error(ErrBadRequest, running_message)
            if kind == "repository_profile" and current_material is not None:
                from testing_agent.services.repository_profile_candidates import (
                    ensure_profile_candidate_chain,
                )

                await ensure_profile_candidate_chain(
                    self.repository.session, task=current_task, stage=stage
                )
            attempt, _ = await dispatch_auxiliary_execution(
                self.repository.session,
                task=current_task,
                actor_id=user_id,
                request_id=auxiliary_request_id,
                execution_id=run_id,
                connection_id=llm_connection_id,
                source=snapshot,
                config=config,
                trigger_type=trigger_type,
                request_signature=auxiliary_signature,
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
