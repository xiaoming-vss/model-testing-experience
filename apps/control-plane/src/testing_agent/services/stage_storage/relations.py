"""Version-scoped functional case relation graphs for direct stages."""

import json
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest, ErrNotFound, dynamic_error
from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.services.ai_task_output import generated_function_cases
from testing_agent.services.personal_authorization import require_personal_connection
from testing_agent.services.stage_storage.dispatch import dispatch_stage_attempt
from testing_agent.services.stage_storage.views import attempt_source


async def find_leaf(session: AsyncSession, attempt_id: str):
    return (
        await session.execute(
            select(AiGenerationAttempt, AiGenerateTask)
            .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
            .join(AiGenerateTask, AiGenerateTask.task_id == AiGenerationStage.task_id)
            .where(
                AiGenerationAttempt.id == attempt_id,
                AiGenerationStage.stage == "detailed_cases",
                AiGenerateTask.task_type == "functional_case_generate",
                AiGenerateTask.requirement_id != "",
            )
        )
    ).one_or_none()


async def _version(session: AsyncSession, task: AiGenerateTask, attempt_id: str):
    return await session.scalar(
        select(AiGenerateStageVersion).where(
            AiGenerateStageVersion.task_id == task.task_id,
            AiGenerateStageVersion.stage == "detailed_cases",
            AiGenerateStageVersion.attempt_id == attempt_id,
        )
    )


async def graph_view(session: AsyncSession, task: AiGenerateTask, leaf: AiGenerationAttempt):
    version = await _version(session, task, leaf.id)
    latest = await graph_for_version(session, task, version) if version else None
    result = await graph_for_version(session, task, version, success_only=True) if version else None
    snapshot = leaf.input_snapshot_json or {}
    config = deepcopy(snapshot.get("config") or {}) if isinstance(snapshot, dict) else {}
    if not isinstance(config, dict):
        config = {}
    if result and result.output_content:
        config["caseRelations"] = json.loads(result.output_content)
    else:
        config.pop("caseRelations", None)
    graph_active = latest and latest.status in {"pending", "queued", "claimed", "running"}
    graph_failed = latest and latest.status in {"failed", "error", "canceled"}
    status = latest.status if latest is not None and (graph_active or graph_failed) else "success"
    return {
        "runId": leaf.id,
        "taskId": task.task_id,
        "requirementId": task.requirement_id,
        "sprintId": task.sprint_id,
        "projectId": task.project_id,
        "triggerUserId": leaf.requested_by or "",
        "triggerType": "manual",
        "status": status,
        "checkpointEnabled": True,
        "generationChainManaged": True,
        "currentStage": "relation_analysis" if graph_active or graph_failed else "completed",
        "stageStatus": status,
        "snapshotJson": attempt_source(leaf),
        "errorMessage": (latest.error_message or "") if graph_failed and latest else "",
        "configJson": config,
        "resultYaml": version.artifact_content if version else leaf.output_content or "",
        "resultSummaryJson": {},
        "reviewStatus": "approved" if version else "pending",
        "importStatus": "pending",
        "reviewerUserId": version.reviewer_user_id if version else "",
        "reviewedAt": version.reviewed_at if version else None,
        "reviewComment": version.review_comment if version else "",
        "durationMs": 0,
    }


async def graph_for_version(
    session: AsyncSession,
    task: AiGenerateTask,
    version: AiGenerateStageVersion,
    *,
    success_only: bool = False,
):
    """Find a graph that explicitly references the approved case version."""
    attempts = list(
        (
            await session.scalars(
                select(AiGenerationAttempt)
                .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
                .where(
                    AiGenerationStage.task_id == task.task_id,
                    AiGenerationStage.stage == "relation_analysis",
                )
                .order_by(
                    AiGenerationAttempt.created_at.desc(), AiGenerationAttempt.attempt_no.desc()
                )
            )
        ).all()
    )
    for attempt in attempts:
        if success_only and (attempt.status != "success" or not attempt.output_content):
            continue
        snapshot = attempt.input_snapshot_json or {}
        versioning = snapshot.get("versioning") if isinstance(snapshot, dict) else None
        base = versioning.get("baseVersionId") if isinstance(versioning, dict) else None
        if base == version.version_id:
            return attempt
    return None


async def launch_graph(
    session: AsyncSession,
    task: AiGenerateTask,
    source_attempt_id: str,
    actor: str,
    connection_id: str,
) -> AiGenerationAttempt:
    """Caller authorizes and locks the task; all changes commit together."""
    version = await _version(session, task, source_attempt_id)
    if version is None:
        raise dynamic_error(ErrBadRequest, "完整用例审核通过后才能生成图谱")
    version = await session.scalar(
        select(AiGenerateStageVersion)
        .where(AiGenerateStageVersion.version_id == version.version_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if version is None:
        raise ErrNotFound()
    leaf = await session.scalar(
        select(AiGenerationAttempt).where(AiGenerationAttempt.id == version.attempt_id)
    )
    if leaf is None:
        raise ErrNotFound()
    cases = generated_function_cases(SimpleNamespace(result_yaml=version.artifact_content))
    ids = [str(item.get("case_id") or item.get("caseId") or "").strip() for item in cases]
    if not ids or any(not value for value in ids) or len(set(ids)) != len(ids):
        raise dynamic_error(ErrBadRequest, "用例缺少唯一的 case_id，请重新生成并审核用例")
    await require_personal_connection(session, actor, "llm", connection_id, task.project_id)
    previous = await graph_for_version(session, task, version, success_only=True)
    snapshot = leaf.input_snapshot_json or {}
    config = deepcopy(snapshot.get("config") or {}) if isinstance(snapshot, dict) else {}
    if not isinstance(config, dict) or not isinstance(config.get("requirementAnalysis"), dict):
        raise dynamic_error(ErrBadRequest, "该版本缺少图谱所需的测试需求分析，请重新生成并审核")
    config.pop("revisionInstruction", None)
    config["resultYaml"] = json.dumps({"cases": cases}, ensure_ascii=False)
    if previous and previous.status == "success" and previous.output_content:
        config["caseRelations"] = json.loads(previous.output_content)
    else:
        config.pop("caseRelations", None)
    stage = await session.scalar(
        select(AiGenerationStage).where(
            AiGenerationStage.task_id == task.task_id,
            AiGenerationStage.stage == "relation_analysis",
        )
    )
    if stage is None:
        stage = AiGenerationStage(
            id=str(uuid4()), task_id=task.task_id, stage="relation_analysis", next_version_no=1
        )
        session.add(stage)
        await session.flush()
    attempt, _ = await dispatch_stage_attempt(
        session,
        task=task,
        stage_id=stage.id,
        request_id=str(uuid4()),
        actor_id=actor,
        input_snapshot={
            "source": deepcopy(attempt_source(leaf)),
            "config": config,
            "llmConnectionId": connection_id,
            "versioning": {"baseVersionId": version.version_id},
        },
    )
    return attempt
