"""One reviewed UI artifact per dispatch, using the existing stage/attempt ledger."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.ai_execution_intent import ExecutionIntent, StageReview
from testing_agent.domain.ui_generation_artifacts import UI_FIELDS, UI_STAGES
from testing_agent.models.ai_generate_task import AiGenerateTaskRun
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services.ai_stage_workflow import GenerationStageWorkflow
from testing_agent.services.ai_task_output import dump_run, normalize_config_json
from testing_agent.services.project_access import ProjectAction
from testing_agent.services.ui_generation_contracts import is_ui_workflow, validate_ui_output


class UiGenerationWorkflow(GenerationStageWorkflow):
    async def checked_run(
        self, run_id: str, body: dict[str, Any], user_id: str, action: ProjectAction
    ) -> AiGenerateTaskRun:
        run = await self.owned_run(user_id, run_id, "ui", action=action)
        stage = str(body.get("stage") or body.get("currentStage") or run.current_stage)
        effective_stage = "ui_yaml" if run.current_stage == "completed" else run.current_stage
        if (
            not is_ui_workflow(run)
            or stage != effective_stage
            or stage not in UI_STAGES
            or run.review_status != "pending"
            or run.import_status == "imported"
        ):
            raise ErrBadRequest()
        return run

    @staticmethod
    def stage_value(run: AiGenerateTaskRun, stage: str, body: dict[str, Any]) -> Any:
        if stage == "ui_yaml":
            return validate_ui_output(run, stage, body.get("resultYaml", run.result_yaml))
        field = UI_FIELDS[stage]
        edits = normalize_config_json(body.get("configJson")) if "configJson" in body else {}
        if set(edits) - {field}:
            raise dynamic_error(ErrBadRequest, "仅能编辑当前阶段 JSON")
        return validate_ui_output(run, stage, edits.get(field, (run.config_json or {}).get(field)))

    async def save_output(self, run_id: str, body: dict[str, Any], user_id: str) -> dict:
        run = await self.checked_run(run_id, body, user_id, "write")
        stage = "ui_yaml" if run.current_stage == "completed" else run.current_stage
        if run.status not in {"waiting_review", "success"}:
            raise ErrBadRequest()
        value = self.stage_value(run, stage, body)
        if stage == "ui_yaml":
            run.result_yaml = value
        else:
            run.config_json = {**(run.config_json or {}), UI_FIELDS[stage]: value}
        await self.execution.save(
            self.repository.session, run, intent=ExecutionIntent(actor_id=user_id)
        )
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def review_output(
        self,
        run_id: str,
        body: dict[str, Any],
        user_id: str,
        *,
        continue_after: bool = True,
        retain_rejected_draft: bool = False,
    ) -> dict:
        run = await self.checked_run(run_id, body, user_id, "review")
        stage = "ui_yaml" if run.current_stage == "completed" else run.current_stage
        if run.status not in {"waiting_review", "success"}:
            raise ErrBadRequest()
        action = str(body.get("action") or "approve")
        if action not in {"approve", "reject"}:
            raise ErrBadRequest()
        intent = ExecutionIntent(
            actor_id=user_id,
            review=StageReview(
                stage,
                "approved" if action == "approve" else "rejected",
                str(body.get("reviewComment") or ""),
            ),
        )
        dispatch = None
        if action == "approve":
            self.stage_value(run, stage, {})
            if stage == "ui_yaml":
                run.status = "success"
                run.stage_status = "completed"
                run.review_status = "approved"
                run.reviewer_user_id = user_id
                run.reviewed_at = datetime.now(UTC)
                run.review_comment = str(body.get("reviewComment") or "")
            elif not continue_after:
                run.status = "success"
                run.stage_status = "completed"
                run.error_message = ""
            else:
                latest = await self.repository.get_latest_ai_dispatch(run_id)
                if latest is None or latest.status in {"pending", "claimed", "running"}:
                    raise ErrBadRequest()
                connection = await self.stage_connection(
                    run, body, user_id, latest.llm_connection_id
                )
                run.current_stage = UI_STAGES[UI_STAGES.index(stage) + 1]
                run.status = "pending"
                run.stage_status = "pending"
                run.error_message = ""
                run.config_json = {
                    k: v
                    for k, v in (run.config_json or {}).items()
                    if k not in {"revisionInstruction", "resultYaml"}
                }
                intent = replace(intent, llm_connection_id=connection)
                dispatch = WorkerTask(
                    domain="ai",
                    task_id=self.new_id(),
                    task_type="ui_case_generate",
                    run_id=run_id,
                    status="pending",
                )
                self.repository.add(dispatch)
        else:
            if retain_rejected_draft:
                run.status = "success"
                run.stage_status = "completed"
            else:
                run.status = "canceled"
                run.stage_status = "failed"
            run.review_status = "rejected"
            run.reviewer_user_id = user_id
            run.reviewed_at = datetime.now(UTC)
            run.review_comment = str(body.get("reviewComment") or "")
        await self.execution.save(self.repository.session, run, intent=intent, worker=dispatch)
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def regenerate(
        self, run_id: str, body: dict[str, Any], user_id: str, *, retry: bool = False
    ) -> dict:
        run = await self.checked_run(run_id, body, user_id, "execute")
        stage = "ui_yaml" if run.current_stage == "completed" else run.current_stage
        if retry:
            if run.status not in {"failed", "error"}:
                raise ErrBadRequest()
        elif run.status not in {"waiting_review", "success"}:
            raise ErrBadRequest()
        latest = await self.repository.get_latest_ai_dispatch(run_id)
        if latest is None or latest.status in {"pending", "claimed", "running"}:
            raise ErrBadRequest()
        config = dict(run.config_json or {})
        if not retry:
            instruction = str(body.get("revisionInstruction") or "").strip()
            if not instruction:
                raise ErrBadRequest()
            value = self.stage_value(run, stage, body)
            config[UI_FIELDS.get(stage, "resultYaml")] = value
            config["revisionInstruction"] = instruction
        connection = await self.stage_connection(run, body, user_id, latest.llm_connection_id)
        run.config_json = config
        run.current_stage = stage
        run.status = "pending"
        run.stage_status = "pending"
        run.error_message = ""
        dispatch = WorkerTask(
            domain="ai",
            task_id=self.new_id(),
            task_type="ui_case_generate",
            run_id=run_id,
            status="pending",
        )
        self.repository.add(dispatch)
        await self.execution.save(
            self.repository.session,
            run,
            intent=ExecutionIntent(
                actor_id=user_id,
                llm_connection_id=connection,
                operation="retry" if retry else "revise",
            ),
            worker=dispatch,
        )
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)
