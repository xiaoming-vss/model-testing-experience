"""direct stage launch; caller owns authorization and transaction."""

from copy import deepcopy
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import select

from testing_agent.core.errors import ErrBadRequest, ErrNotFound, dynamic_error
from testing_agent.db.savepoint import ensure_outer_transaction
from testing_agent.domain.generation_chain import (
    STAGE_CONFIG_FIELDS,
    artifact_value,
    stage_names,
    upstream_stages,
)
from testing_agent.domain.request_identity import request_signature
from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generate_task_source_archive import AiGenerateTaskSourceArchive
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.schemas.generation_chain import GenerationChainRunRequest
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.ai_task_output import build_generate_run_snapshot, normalize_config_json
from testing_agent.services.personal_authorization import require_personal_connection
from testing_agent.services.stage_storage.dispatch import (
    dispatch_stage_attempt,
    replay_stage_attempt,
    reserve_worker_identity,
)
from testing_agent.services.stage_storage.upstream import select_upstream_versions
from testing_agent.services.stage_storage.views import attempt_source

if TYPE_CHECKING:
    from testing_agent.services.generation_chain import GenerationChainService


async def _stages(
    chain: "GenerationChainService", task: AiGenerateTask, kind: DesignKind
) -> dict[str, AiGenerationStage]:
    session = chain.tasks.session
    from testing_agent.repositories.standalone_execution import lock_or_create_stage

    stages = {}
    for name in stage_names(kind):
        stages[name], _ = await lock_or_create_stage(session, task.task_id, name)
    return stages


async def _known_source(
    chain: "GenerationChainService", version: AiGenerateStageVersion
) -> dict[str, Any]:
    attempt = await chain.tasks.session.scalar(
        select(AiGenerationAttempt).where(AiGenerationAttempt.id == version.attempt_id)
    )
    return deepcopy(attempt_source(attempt)) if attempt else {}


async def _start_stage(
    chain: "GenerationChainService",
    task: AiGenerateTask,
    kind: DesignKind,
    stage: str,
    body: GenerationChainRunRequest,
    user_id: str,
) -> AiGenerationAttempt:
    """Create or reuse a direct Worker dispatch, without committing caller's transaction.

    Caller must lock and authorize task and roll back on error. Batch changes,
    stage attempt and worker queue updates remain in the same transaction.
    """
    if stage not in stage_names(kind):
        raise ErrBadRequest()
    session = chain.tasks.session
    worker_id = str(body.request_id) if body.request_id else str(uuid4())
    if body.refresh_inputs and (kind != "ui" or stage != "ui_surface"):
        raise dynamic_error(ErrBadRequest, "只能在元素控件清单阶段更换 UI 生成输入")
    if body.function_case_ids is not None and (kind != "ui" or stage != "ui_surface"):
        raise ErrBadRequest()
    config = normalize_config_json(body.config_json)
    if set(config) & (set(STAGE_CONFIG_FIELDS.values()) | {"resultYaml", "revisionInstruction"}):
        raise dynamic_error(ErrBadRequest, "不能通过配置直接指定阶段产物，请先审核上游阶段")
    signature = request_signature(
        "generation-stage-run",
        {
            "kind": kind,
            "stage": stage,
            "connectionId": body.connection_id,
            "instruction": body.instruction,
            "config": config,
            "refreshInputs": body.refresh_inputs,
            "functionCaseIds": body.function_case_ids,
            "upstreamVersions": body.upstream_versions,
        },
    )
    await require_personal_connection(session, user_id, "llm", body.connection_id, task.project_id)
    attempt_id = str(uuid4())
    worker, replay = await reserve_worker_identity(session, task, worker_id, attempt_id)
    if replay:
        return await replay_stage_attempt(
            session,
            worker=worker,
            task=task,
            stage_name=stage,
            actor_id=user_id,
            operation="generate",
            signature=signature,
        )
    selected = await select_upstream_versions(session, task, kind, stage, body.upstream_versions)
    stages = await _stages(chain, task, kind)
    source: dict[str, Any] = {}
    if selected:
        # Preserve exact existing input of an approved upstream attempt. If the
        # input is genuinely unavailable, construct new inputs and never infer
        # or write fictitious history into the selected version.
        parent_stage = upstream_stages(kind, stage)[0]
        source = await _known_source(chain, selected[parent_stage])
        if kind == "function" and parent_stage == "requirement_analysis":
            context = selected[parent_stage].artifact_context_json or {}
            stored_source = context.get("functionalSource") if isinstance(context, dict) else None
            if (
                isinstance(stored_source, dict)
                and stored_source.get("requirementUnderstandingVersion")
                and "sourceContent" in stored_source
            ):
                source = {**source, **deepcopy(stored_source)}
            elif not source.get("requirementUnderstandingVersion"):
                source = {}
    if kind == "ui":
        first = stages["ui_surface"]
        if stage != "ui_surface" and first.source_snapshot_json:
            source = deepcopy(first.source_snapshot_json)
        if (
            stage == "ui_surface"
            and first.source_batch_id
            and body.function_case_ids is not None
            and not body.refresh_inputs
        ):
            raise dynamic_error(ErrBadRequest, "更换功能用例需要重新开始 UI 生成链")
    if not source:
        source = await build_generate_run_snapshot(
            chain.tasks,
            kind,
            task,
            attempt_id,
            body.instruction or "",
            worker_task_id=worker_id,
            understanding_version_id=selected["feature_understanding"].version_id
            if "feature_understanding" in selected
            else "",
        )
    source["instruction"] = body.instruction or ""
    if kind == "requirement_analysis":
        requirement = await chain.tasks.get_requirement(task.requirement_id)
        if requirement is None:
            raise ErrNotFound()
        if not str(requirement.document_file_id or "").strip():
            from testing_agent.core.errors import ErrRequirementFileMissing

            raise ErrRequirementFileMissing()
        source["workflowVersion"] = 2
    if kind == "api":
        source["apiWorkflowVersion"] = "api_two_stage/1.0"
    if kind == "ui" and stage == "ui_surface":
        first = stages[stage]
        if not first.source_batch_id or body.refresh_inputs:
            if first.active_attempt_id:
                raise dynamic_error(ErrBadRequest, "当前阶段正在执行，请等待完成后再更换输入")
            archive = await session.scalar(
                select(AiGenerateTaskSourceArchive).where(
                    AiGenerateTaskSourceArchive.task_id == task.task_id
                )
            )
            if archive is None or not archive.file_id:
                raise dynamic_error(ErrBadRequest, "请先上传源码包")
            ids = body.function_case_ids
            if ids is not None and (
                not ids or len(set(ids)) != len(ids) or any(not item for item in ids)
            ):
                raise ErrBadRequest()
            cases = await chain.tasks.list_ui_source_cases(task.requirement_id, ids)
            if not cases or (ids is not None and {case["caseId"] for case in cases} != set(ids)):
                raise dynamic_error(ErrBadRequest, "请选择当前需求下至少一条正式功能用例")
            if body.refresh_inputs and first.source_batch_id:
                from testing_agent.services.stage_storage.ui_batch import detach_old_ui_batch

                await detach_old_ui_batch(session, task.task_id)
            batch = str(uuid4())
            source.update(
                {
                    "sourceArchiveFileId": archive.file_id,
                    "sourceArchive": {
                        "filename": archive.filename,
                        "sha256": archive.sha256,
                        "sizeBytes": archive.size_bytes,
                    },
                    "functionalCases": cases,
                    "uiWorkflowVersion": "ui_three_stage/1.0",
                    "uiSourceBatchId": batch,
                }
            )
            first.source_batch_id = batch
            first.source_snapshot_json = {
                key: deepcopy(source[key])
                for key in (
                    "sourceContent",
                    "functionalCases",
                    "sourceArchiveFileId",
                    "sourceArchive",
                    "sourceType",
                    "uiWorkflowVersion",
                    "uiSourceBatchId",
                    "instruction",
                )
                if key in source
            }
        else:
            source = deepcopy(first.source_snapshot_json or source)
    for parent, version in selected.items():
        if parent in STAGE_CONFIG_FIELDS and parent in stage_names(kind):
            config[STAGE_CONFIG_FIELDS[parent]] = artifact_value(
                parent, version.artifact_content, version.artifact_format
            )
    snapshot = {
        "source": source,
        "config": config,
        "currentOutput": "",
        "llmConnectionId": body.connection_id,
        "requestSignature": signature,
        "versioning": {
            "baseVersionId": "",
            "upstreamVersions": {key: version.version_id for key, version in selected.items()},
        },
    }
    attempt, _ = await dispatch_stage_attempt(
        session,
        task=task,
        stage_id=stages[stage].id,
        request_id=worker_id,
        actor_id=user_id,
        input_snapshot=snapshot,
        attempt_id=attempt_id,
        reserved_worker=worker,
    )
    return attempt


async def start_stage(
    chain: "GenerationChainService",
    task: AiGenerateTask,
    kind: DesignKind,
    stage: str,
    body: GenerationChainRunRequest,
    user_id: str,
) -> AiGenerationAttempt:
    """Roll back the queue reservation and input changes together on error."""
    session = chain.tasks.session
    await session.run_sync(ensure_outer_transaction)
    async with session.begin_nested():
        return await _start_stage(chain, task, kind, stage, body, user_id)
