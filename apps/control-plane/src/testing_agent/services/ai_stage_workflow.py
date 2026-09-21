from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from testing_agent.core.enums import ImportStatus, ReviewStatus, RunStatus, StageStatus
from testing_agent.core.errors import (
    ErrBadRequest,
    ErrNotFound,
    dynamic_error,
)
from testing_agent.core.sid import new_id
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.ai_task_access import (
    OwnedRun,
)
from testing_agent.services.ai_task_contracts import (
    FUNCTION_CASE_RELATION_DISPATCH_STATUSES,
    FUNCTION_CASE_RELATION_STAGE,
    FUNCTION_CASE_REVIEW_READY_STATUSES,
    FUNCTION_CASE_REVIEWABLE_STAGES,
    REQUIREMENT_ANALYSIS_FINAL_RUN_STAGES,
    REQUIREMENT_ANALYSIS_FINAL_STAGE,
    REQUIREMENT_ANALYSIS_REVIEW_READY_STATUSES,
    REQUIREMENT_ANALYSIS_REVIEWABLE_STAGES,
    REVISION_INSTRUCTION_FIELD,
    next_function_case_stage,
    next_requirement_analysis_stage,
    task_type_for,
)
from testing_agent.services.ai_task_output import (
    dump_run,
    first_present,
    generated_function_cases,
    normalize_config_json,
    normalize_function_stage_config,
    validate_function_candidate_cases,
)
from testing_agent.services.personal_authorization import require_personal_connection


class GenerationStageWorkflow:
    def __init__(
        self,
        *,
        repository: AiGenerateTaskRepository,
        owned_run: OwnedRun,
        id_factory: Callable[[], str] = new_id,
    ):
        self.repository = repository
        self.owned_run = owned_run
        self.new_id = id_factory

    async def stage_connection(self, run, body, user_id, previous_id):
        connection_id = str(
            body.get("connectionId") or body.get("llmConnectionId") or previous_id or ""
        )
        connection = await require_personal_connection(
            self.repository.session, user_id, "llm", connection_id, run.project_id
        )
        return connection.connection_id

    async def save_stage_output(self, run_id: str, body: dict[str, Any], user_id: str) -> dict:
        run = await self.owned_run(user_id, run_id, "function", action="review")
        if (
            not run.checkpoint_enabled
            or run.status != "waiting_review"
            or run.stage_status not in FUNCTION_CASE_REVIEW_READY_STATUSES
            or run.current_stage not in FUNCTION_CASE_REVIEWABLE_STAGES
            or run.review_status != ReviewStatus.PENDING.value
            or getattr(run, "import_status", ImportStatus.PENDING.value)
            == ImportStatus.IMPORTED.value
        ):
            raise dynamic_error(ErrBadRequest, "仅允许保存未审核、未导入且等待审核的当前阶段产物")
        if set(body) - {"stage", "currentStage", "configJson"} or "configJson" not in body:
            raise dynamic_error(ErrBadRequest, "阶段保存仅支持当前阶段的 configJson")
        for key in ("stage", "currentStage"):
            if key in body and body[key] != run.current_stage:
                raise dynamic_error(ErrBadRequest, "不能修改其他阶段的产物")
        field = {"requirement_analysis": "requirementAnalysis", "case_names": "caseNames"}[
            run.current_stage
        ]
        raw_config = normalize_config_json(body["configJson"])
        # Stage editors may send a bare artifact, but cannot change another stage.
        if (set(raw_config) & {"enhancedText", "requirementAnalysis", "caseNames"}) - {field}:
            raise dynamic_error(ErrBadRequest, "不能修改其他阶段的产物")
        edits = normalize_function_stage_config(run.current_stage, raw_config)
        if set(edits) != {field} or not isinstance(edits[field], dict) or not edits[field]:
            raise dynamic_error(ErrBadRequest, "阶段产物必须是当前阶段的非空 JSON 对象")
        run.config_json = {**normalize_config_json(run.config_json), field: edits[field]}
        run.stage_status = StageStatus.WAITING_REVIEW.value
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def save_requirement_analysis_stage_output(
        self, run_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        run = await self.owned_run(user_id, run_id, "requirement_analysis", action="review")
        current_stage = str(body.get("currentStage") or body.get("stage") or run.current_stage)
        is_review_stage = (
            run.checkpoint_enabled
            and current_stage == run.current_stage
            and current_stage in REQUIREMENT_ANALYSIS_REVIEWABLE_STAGES
            and run.status == "waiting_review"
            and run.stage_status in REQUIREMENT_ANALYSIS_REVIEW_READY_STATUSES
        )
        is_final_stage = (
            run.status == RunStatus.SUCCESS.value
            and current_stage == REQUIREMENT_ANALYSIS_FINAL_STAGE
            and run.current_stage in REQUIREMENT_ANALYSIS_FINAL_RUN_STAGES
        )
        if not (is_review_stage or is_final_stage):
            raise ErrBadRequest
        if is_review_stage:
            run.stage_status = StageStatus.WAITING_REVIEW.value
        if "configJson" in body:
            run.config_json = normalize_config_json(body.get("configJson"))
        if "resultYaml" in body:
            run.result_yaml = str(body.get("resultYaml") or "")
        run.result_summary_json = body.get("resultSummaryJson") or run.result_summary_json
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def review_requirement_analysis_stage(
        self, run_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        run = await self.owned_run(user_id, run_id, "requirement_analysis", action="review")
        if (
            not run.checkpoint_enabled
            or run.status != "waiting_review"
            or run.stage_status not in REQUIREMENT_ANALYSIS_REVIEW_READY_STATUSES
        ):
            raise ErrBadRequest

        current_stage = str(body.get("currentStage") or body.get("stage") or "")
        if (
            current_stage != run.current_stage
            or current_stage not in REQUIREMENT_ANALYSIS_REVIEWABLE_STAGES
        ):
            raise ErrBadRequest

        action = str(
            body.get("action")
            or body.get("reviewStatus")
            or body.get("status")
            or body.get("stageStatus")
            or "approve"
        )
        if action == "approved":
            action = "approve"
        if action == "rejected":
            action = "reject"

        run.review_comment = str(body.get("reviewComment") or body.get("comment") or "")
        run.reviewer_user_id = user_id
        run.reviewed_at = datetime.now(UTC)
        if action == "approve":
            latest_task = await self.repository.get_latest_worker_task_by_run_id(run.run_id)
            next_stage = next_requirement_analysis_stage(run.current_stage)
            if latest_task is None or next_stage is None:
                raise ErrBadRequest
            if "configJson" in body:
                run.config_json = normalize_config_json(body.get("configJson"))
            run.status = RunStatus.PENDING.value
            run.current_stage = next_stage
            run.stage_status = StageStatus.PENDING.value
            run.error_message = ""
            self.repository.add(
                WorkerTask(
                    domain="ai",
                    task_id=self.new_id(),
                    task_type=task_type_for("requirement_analysis"),
                    run_id=run.run_id,
                    generate_task_id=run.task_id,
                    llm_connection_id=await self.stage_connection(
                        run, body or {}, user_id, latest_task.llm_connection_id
                    ),
                    status=RunStatus.PENDING.value,
                )
            )
        elif action == "reject":
            run.status = RunStatus.CANCELED.value
            run.stage_status = StageStatus.FAILED.value
        else:
            raise ErrBadRequest
        run._stage_review = (
            current_stage,
            "approved" if action == "approve" else "rejected",
            str(body.get("reviewComment") or body.get("comment") or ""),
        )
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def revise_requirement_analysis_stage(
        self, run_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        run = await self.owned_run(user_id, run_id, "requirement_analysis", action="execute")

        current_stage = str(body.get("currentStage") or body.get("stage") or "")
        is_review_stage = (
            run.checkpoint_enabled
            and run.status == "waiting_review"
            and run.stage_status in REQUIREMENT_ANALYSIS_REVIEW_READY_STATUSES
            and current_stage == run.current_stage
            and current_stage in REQUIREMENT_ANALYSIS_REVIEWABLE_STAGES
        )
        is_final_stage = (
            run.status == RunStatus.SUCCESS.value
            and current_stage == REQUIREMENT_ANALYSIS_FINAL_STAGE
            and run.current_stage in REQUIREMENT_ANALYSIS_FINAL_RUN_STAGES
        )
        if not is_review_stage and not is_final_stage:
            raise ErrBadRequest

        revision_instruction = str(
            body.get(REVISION_INSTRUCTION_FIELD) or body.get("revision_instruction") or ""
        ).strip()
        if not revision_instruction:
            raise ErrBadRequest

        latest_task = await self.repository.get_latest_worker_task_by_run_id(run.run_id)
        if latest_task is None:
            raise ErrBadRequest

        if "configJson" in body:
            run.config_json = normalize_config_json(body.get("configJson"))
        elif not isinstance(run.config_json, dict):
            run.config_json = normalize_config_json(run.config_json)
        if is_final_stage:
            result_yaml = str(body.get("resultYaml") or run.result_yaml or "").strip()
            if not result_yaml:
                raise ErrBadRequest
            run.config_json["resultYaml"] = str(body.get("resultYaml") or run.result_yaml or "")
        run.config_json[REVISION_INSTRUCTION_FIELD] = revision_instruction
        run.status = RunStatus.PENDING.value
        if is_final_stage:
            run.current_stage = REQUIREMENT_ANALYSIS_FINAL_STAGE
        run.stage_status = StageStatus.PENDING.value
        run.error_message = ""
        self.repository.add(
            WorkerTask(
                domain="ai",
                task_id=self.new_id(),
                task_type=task_type_for("requirement_analysis"),
                run_id=run.run_id,
                generate_task_id=run.task_id,
                llm_connection_id=await self.stage_connection(
                    run, body or {}, user_id, latest_task.llm_connection_id
                ),
                status=RunStatus.PENDING.value,
            )
        )
        run._operation = "revise"
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def revise_function_case_stage(
        self, run_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        await self.owned_run(user_id, run_id, "function", action="execute")
        # Refresh under the row lock to observe any concurrent submission.
        run = await self.repository.get_run_for_update(run_id)
        if run is None:
            raise ErrNotFound
        # The locked reload may return a new instance without the transient actor.
        run._actor = user_id
        stage = str(body.get("stage") or body.get("currentStage") or "")
        is_checkpoint = (
            run.checkpoint_enabled
            and run.status == "waiting_review"
            and run.stage_status in FUNCTION_CASE_REVIEW_READY_STATUSES
            and stage == run.current_stage
            and stage in FUNCTION_CASE_REVIEWABLE_STAGES
        )
        is_final = (
            stage == "detailed_cases"
            and run.current_stage in {"detailed_cases", "completed", ""}
            and run.status == RunStatus.SUCCESS.value
        )
        if (
            not (is_checkpoint or is_final)
            or run.review_status != ReviewStatus.PENDING.value
            or run.import_status == ImportStatus.IMPORTED.value
        ):
            raise ErrBadRequest
        instruction = str(body.get("revisionInstruction") or "").strip()
        if not instruction:
            raise ErrBadRequest
        config = dict(normalize_config_json(run.config_json))
        field = {"requirement_analysis": "requirementAnalysis", "case_names": "caseNames"}.get(
            stage
        )
        if field and "configJson" in body:
            edits = normalize_function_stage_config(stage, body["configJson"])
            # Confirmed upstream inputs cannot be edited by a revision request.
            if field not in edits:
                raise ErrBadRequest
            config[field] = edits[field]
        if field:
            current_output = config.get(field)
            if not current_output or (
                isinstance(current_output, str) and not current_output.strip()
            ):
                raise ErrBadRequest
        else:
            current_output = str(body.get("resultYaml", run.result_yaml) or "")
            if not current_output.strip():
                raise ErrBadRequest
            cases = generated_function_cases(SimpleNamespace(result_yaml=current_output))
            if not cases:
                raise ErrBadRequest
            validate_function_candidate_cases(cases)
            config["resultYaml"] = json.dumps({"cases": cases}, ensure_ascii=False)
        latest_task = await self.repository.get_latest_worker_task_by_run_id(run_id)
        if latest_task is None:
            raise ErrBadRequest
        config[REVISION_INSTRUCTION_FIELD] = instruction
        run.config_json = config
        if is_final:
            run.result_yaml = current_output
        run.status = RunStatus.PENDING.value
        run.current_stage = stage
        run.stage_status = StageStatus.PENDING.value
        run.error_message = ""
        self.repository.add(
            WorkerTask(
                domain="ai",
                task_id=self.new_id(),
                task_type=task_type_for("function"),
                run_id=run.run_id,
                generate_task_id=run.task_id,
                llm_connection_id=await self.stage_connection(
                    run, body or {}, user_id, latest_task.llm_connection_id
                ),
                status=RunStatus.PENDING.value,
            )
        )
        run._operation = "revise"
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def review_stage(self, run_id: str, body: dict[str, Any], user_id: str) -> dict:
        run = await self.owned_run(user_id, run_id, "function", action="review")
        if (
            not run.checkpoint_enabled
            or run.status != "waiting_review"
            or run.stage_status not in FUNCTION_CASE_REVIEW_READY_STATUSES
        ):
            raise ErrBadRequest

        current_stage = str(body.get("currentStage") or body.get("stage") or "")
        if (
            current_stage != run.current_stage
            or current_stage not in FUNCTION_CASE_REVIEWABLE_STAGES
        ):
            raise ErrBadRequest

        action = str(
            body.get("action")
            or body.get("reviewStatus")
            or body.get("status")
            or body.get("stageStatus")
            or "approve"
        )
        if action == "approved":
            action = "approve"
        if action == "rejected":
            action = "reject"

        if action == "approve":
            latest_task = await self.repository.get_latest_worker_task_by_run_id(run.run_id)
            next_stage = next_function_case_stage(run.current_stage)
            if latest_task is None or next_stage is None:
                raise ErrBadRequest
            run.status = RunStatus.PENDING.value
            run.current_stage = next_stage
            run.stage_status = StageStatus.PENDING.value
            run.error_message = ""
            self.repository.add(
                WorkerTask(
                    domain="ai",
                    task_id=self.new_id(),
                    task_type=task_type_for("function"),
                    run_id=run.run_id,
                    generate_task_id=run.task_id,
                    llm_connection_id=await self.stage_connection(
                        run, body or {}, user_id, latest_task.llm_connection_id
                    ),
                    status=RunStatus.PENDING.value,
                )
            )
        elif action == "reject":
            run.status = RunStatus.CANCELED.value
            run.stage_status = StageStatus.FAILED.value
        else:
            raise ErrBadRequest
        run._stage_review = (
            current_stage,
            "approved" if action == "approve" else "rejected",
            str(body.get("reviewComment") or body.get("comment") or ""),
        )
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def retry_stage(
        self,
        run_id: str,
        body: dict[str, Any] | None,
        user_id: str,
        *,
        kind: str = "function",
    ) -> dict:
        await self.owned_run(user_id, run_id, kind, action="execute")
        run = await self.repository.get_run_for_update(run_id)
        if run is None:
            raise ErrNotFound
        # The locked reload may return a new instance without the transient actor.
        run._actor = user_id
        allowed_stages = (
            {*REQUIREMENT_ANALYSIS_REVIEWABLE_STAGES, REQUIREMENT_ANALYSIS_FINAL_STAGE}
            if kind == "requirement_analysis"
            else {*FUNCTION_CASE_REVIEWABLE_STAGES, "detailed_cases"}
        )
        payload = body or {}
        stage = str(payload.get("stage") or payload.get("currentStage") or run.current_stage)
        if (
            run.status not in {"failed", "error"}
            # Older retries changed only this field without enqueueing a task.
            or run.stage_status not in {"failed", "retrying"}
            or stage != run.current_stage
            or stage not in allowed_stages
            or run.review_status != ReviewStatus.PENDING.value
            or run.import_status == ImportStatus.IMPORTED.value
        ):
            raise ErrBadRequest
        latest_task = await self.repository.get_latest_worker_task_by_run_id(run_id)
        if latest_task is None or latest_task.status in {"pending", "claimed", "running"}:
            raise ErrBadRequest
        # Retain upstream outputs and any failed revision's instruction for this attempt.
        run.status = RunStatus.PENDING.value
        run.stage_status = StageStatus.PENDING.value
        run.error_message = ""
        self.repository.add(
            WorkerTask(
                domain="ai",
                task_id=self.new_id(),
                task_type=task_type_for(kind),
                run_id=run.run_id,
                generate_task_id=run.task_id,
                llm_connection_id=await self.stage_connection(
                    run, body or {}, user_id, latest_task.llm_connection_id
                ),
                status=RunStatus.PENDING.value,
            )
        )
        run._operation = "retry"
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def generate_relation_analysis(
        self, run_id: str, body: dict[str, Any] | None, user_id: str
    ) -> dict:
        """审核通过后按用户触发派发图谱分析；重复点击基于最新用例重新生成。"""

        await self.owned_run(user_id, run_id, "function", action="execute")
        run = await self.repository.get_run_for_update(run_id)
        if run is None:
            raise ErrNotFound
        # The locked reload may return a new instance without the transient actor.
        run._actor = user_id
        if (
            run.current_stage == FUNCTION_CASE_RELATION_STAGE
            and run.status in FUNCTION_CASE_RELATION_DISPATCH_STATUSES
        ):
            raise dynamic_error(ErrBadRequest, "图谱正在生成中，请等待完成后再试")
        if run.review_status != ReviewStatus.APPROVED.value:
            raise dynamic_error(ErrBadRequest, "候选结果审核通过后才能生成图谱")
        if not (
            run.status == RunStatus.SUCCESS.value
            or (
                run.status in {"failed", "error"}
                and run.current_stage == FUNCTION_CASE_RELATION_STAGE
            )
        ):
            raise ErrBadRequest
        latest_task = await self.repository.get_latest_worker_task_by_run_id(run_id)
        if latest_task is None or latest_task.status in FUNCTION_CASE_RELATION_DISPATCH_STATUSES:
            raise ErrBadRequest
        cases = generated_function_cases(run)
        if not cases:
            raise ErrBadRequest
        case_ids = [str(first_present(case, "case_id", "caseId") or "").strip() for case in cases]
        if any(not case_id for case_id in case_ids):
            raise dynamic_error(
                ErrBadRequest, "用例缺少平台签发的 case_id，请重新生成用例后再生成图谱"
            )
        if len(case_ids) != len(set(case_ids)):
            raise dynamic_error(ErrBadRequest, "用例 case_id 重复，请重新生成用例后再生成图谱")
        config = dict(normalize_config_json(run.config_json))
        config.pop(REVISION_INSTRUCTION_FIELD, None)
        # 上一次关系产物随 config 进入派发快照，skill 据此沿用既有流程/节点/连线 ID。
        config["resultYaml"] = json.dumps({"cases": cases}, ensure_ascii=False)
        run.config_json = config
        run.status = RunStatus.PENDING.value
        run.current_stage = FUNCTION_CASE_RELATION_STAGE
        run.stage_status = StageStatus.PENDING.value
        run.error_message = ""
        self.repository.add(
            WorkerTask(
                domain="ai",
                task_id=self.new_id(),
                task_type=task_type_for("function"),
                run_id=run.run_id,
                generate_task_id=run.task_id,
                llm_connection_id=await self.stage_connection(
                    run, body or {}, user_id, latest_task.llm_connection_id
                ),
                status=RunStatus.PENDING.value,
            )
        )
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)
