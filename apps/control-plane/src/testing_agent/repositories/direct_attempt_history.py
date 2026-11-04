"""Bounded requirement-chain attempt history without loading artifact bodies."""

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest
from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion as Version
from testing_agent.models.ai_generate_task import AiGenerateTask as Task
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport as Import
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt as Attempt
from testing_agent.models.ai_generation_stage import AiGenerationStage as Stage


async def direct_history_rows(
    session: AsyncSession,
    task_id: str | None,
    page: int,
    page_size: int,
    pipeline_filter: str,
    *,
    task_conditions: tuple = (),
):
    allowed = {
        "all",
        "running",
        "review_pending",
        "approved",
        "import_pending",
        "imported",
        "rejected",
        "failed",
        "canceled",
    }
    if page < 1 or not 1 <= page_size <= 100 or pipeline_filter not in allowed:
        raise ErrBadRequest()
    imported = (
        select(Import.id).where(Import.version_id == Version.version_id).correlate(Version).exists()
    )
    pending = and_(
        Attempt.status == "success",
        Version.id.is_(None),
        Attempt.invalidated_at.is_(None),
        func.length(Attempt.output_content) > 0,
    )
    pipeline = case(
        (Attempt.status.in_(["failed", "error"]), "failed"),
        (Attempt.status == "canceled", "canceled"),
        (Attempt.invalidated_reason == "审核未通过，候选产物已丢弃", "rejected"),
        (Attempt.status.in_(["pending", "queued", "claimed", "running"]), "running"),
        (and_(Version.id.is_not(None), imported), "imported"),
        (Version.id.is_not(None), "import_pending"),
        else_="review_pending",
    )
    query = (
        select(
            Attempt.id.label("attempt_id"),
            Attempt.status,
            Attempt.requested_by,
            Attempt.created_at,
            Attempt.started_at,
            Attempt.finished_at,
            Attempt.error_message,
            Attempt.invalidated_reason,
            func.coalesce(func.length(Attempt.output_content), 0).label("output_length"),
            Stage.stage,
            Task.task_id,
            Task.project_id,
            Task.sprint_id,
            Task.requirement_id,
            Version.version_id,
            Version.reviewer_user_id,
            Version.reviewed_at,
            Version.review_comment,
        )
        .select_from(Attempt)
        .join(Stage, Stage.id == Attempt.stage_id)
        .join(Task, Task.task_id == Stage.task_id)
        .outerjoin(
            Version,
            and_(
                Version.task_id == Task.task_id,
                Version.stage == Stage.stage,
                Version.attempt_id == Attempt.id,
            ),
        )
        .where(Task.requirement_id != "", *task_conditions)
    )
    if task_id is not None:
        query = query.where(Task.task_id == task_id)
    filtered = query
    if pipeline_filter != "all":
        filtered = filtered.where(
            Version.id.is_not(None)
            if pipeline_filter == "approved"
            else pipeline == pipeline_filter
        )
    sub = filtered.subquery()
    counts = {
        str(key): int(value)
        for key, value in (
            await session.execute(select(sub.c.status, func.count()).group_by(sub.c.status))
        ).all()
    }
    pending_count = await session.scalar(
        select(func.count()).select_from(filtered.where(pending).subquery())
    )
    ordering = (Attempt.created_at.desc(), Attempt.id.desc())
    rows = (
        await session.execute(
            filtered.order_by(*ordering).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    latest = (
        rows[0]
        if page == 1 and pipeline_filter == "all" and rows
        else (await session.execute(query.order_by(*ordering).limit(1))).first()
    )
    ids = list({row.version_id for row in [*rows, *([latest] if latest else [])] if row.version_id})
    imports = (
        (
            await session.execute(
                select(Import.version_id, Import.target_type, Import.target_id, Import.imported_at)
                .where(Import.version_id.in_(ids))
                .order_by(Import.imported_at, Import.id)
            )
        ).all()
        if ids
        else []
    )
    return (
        rows,
        counts,
        int(pending_count or 0),
        latest,
        imports,
    )
