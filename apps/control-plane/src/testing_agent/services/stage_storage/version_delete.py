"""version deletion and direct dependent-draft invalidation."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest, ErrNotFound, dynamic_error
from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage


def _depends(snapshot: Any, version_id: str) -> bool:
    if not isinstance(snapshot, dict):
        return False
    versioning = snapshot.get("versioning")
    upstream = versioning.get("upstreamVersions") if isinstance(versioning, dict) else None
    source = snapshot.get("source")
    source_version = (
        source.get("requirementUnderstandingVersion") if isinstance(source, dict) else None
    )
    return (
        (isinstance(versioning, dict) and versioning.get("baseVersionId") == version_id)
        or (isinstance(upstream, dict) and version_id in upstream.values())
        or (isinstance(source_version, dict) and source_version.get("versionId") == version_id)
    )


async def delete_stage_version(session: AsyncSession, task: AiGenerateTask, version_id: str) -> int:
    """Delete a version and invalidate dependent drafts, without committing.

    The caller must own and lock the task, verify permission and roll back on
    error. Stage creation locks upstream versions before enqueueing attempts.
    """
    version = await session.scalar(
        select(AiGenerateStageVersion)
        .where(
            AiGenerateStageVersion.task_id == task.task_id,
            AiGenerateStageVersion.version_id == version_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if version is None:
        raise ErrNotFound()
    task_ids = {task.task_id}
    if task.task_type == "requirement_analysis" and version.stage == "feature_understanding":
        related = await session.scalar(
            select(AiGenerateTask.task_id)
            .where(
                AiGenerateTask.requirement_id == task.requirement_id,
                AiGenerateTask.task_type == "functional_case_generate",
            )
            .order_by(AiGenerateTask.created_at.desc(), AiGenerateTask.id.desc())
            .limit(1)
        )
        if related:
            task_ids.add(related)
    try:
        # Nonblocking current reads avoid waiting behind a Worker which already
        # holds a stage/attempt while this transaction holds the version lock.
        active = list(
            (
                await session.scalars(
                    select(AiGenerationAttempt)
                    .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
                    .where(
                        AiGenerationStage.task_id.in_(task_ids),
                        AiGenerationAttempt.status.in_({"pending", "queued", "claimed", "running"}),
                    )
                    .order_by(AiGenerationAttempt.id)
                    .with_for_update(nowait=True)
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        if any(_depends(attempt.input_snapshot_json, version_id) for attempt in active):
            raise dynamic_error(ErrBadRequest, "该版本正被运行中的阶段使用，请等待运行结束")
        attempts = list(
            (
                await session.scalars(
                    select(AiGenerationAttempt)
                    .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
                    .where(AiGenerationStage.task_id.in_(task_ids))
                    .order_by(AiGenerationAttempt.id)
                    .with_for_update(nowait=True)
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        # A locking read sees versions committed while this transaction waited
        # for the parent lock, even under MySQL REPEATABLE READ.
        versioned_ids = set(
            (
                await session.scalars(
                    select(AiGenerateStageVersion.attempt_id)
                    .where(AiGenerateStageVersion.task_id.in_(task_ids))
                    .with_for_update(nowait=True)
                )
            ).all()
        )
    except OperationalError as exc:
        if (getattr(exc.orig, "args", ()) or (None,))[0] in {1205, 3572}:
            raise dynamic_error(ErrBadRequest, "阶段仍在处理回传，请稍后重试") from exc
        raise
    invalidated = 0
    for attempt in attempts:
        if attempt.id in versioned_ids or attempt.invalidated_at is not None:
            continue
        if not _depends(attempt.input_snapshot_json, version_id):
            continue
        attempt.invalidated_at = datetime.now(UTC)
        attempt.invalidated_reason = "上游版本已删除，请重新生成该阶段"
        if attempt.output_content and attempt.status == "success":
            invalidated += 1
    await session.execute(
        delete(AiGenerateVersionImport).where(AiGenerateVersionImport.version_id == version_id)
    )
    await session.delete(version)
    await session.flush()
    return invalidated
