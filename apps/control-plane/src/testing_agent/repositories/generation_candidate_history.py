"""Bounded execution history based on candidates and their review receipts."""

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest
from testing_agent.models.ai_generate_import import AiGenerateImport as Import
from testing_agent.models.ai_generate_task import AiGenerateTask as Task
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt as Attempt
from testing_agent.models.ai_generation_stage import AiGenerationStage as Stage
from testing_agent.models.generation_candidates import AiGenerationCandidate as Candidate
from testing_agent.models.generation_candidates import AiGenerationReviewReceipt as Review
from testing_agent.models.generation_candidates import RequirementGenerationChain as Chain


async def candidate_history_rows(
    session: AsyncSession,
    task_id: str | None,
    page: int,
    page_size: int,
    pipeline_filter: str,
    *,
    task_conditions: tuple = (),
):
    if (
        page < 1
        or not 1 <= page_size <= 100
        or pipeline_filter
        not in {
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
    ):
        raise ErrBadRequest()
    review_id = (
        select(Review.receipt_id)
        .where(
            Review.stage_id == Stage.id,
            Review.attempt_id == Attempt.id,
            Review.candidate_id == Candidate.candidate_id,
            Review.decision == "adopted",
        )
        .order_by(Review.created_at.desc(), Review.receipt_id.desc())
        .limit(1)
        .correlate(Stage, Attempt, Candidate)
        .scalar_subquery()
    )
    imported = (
        select(Import.import_id)
        .where(
            Import.source_kind == "current",
            Import.source_attempt_id == Attempt.id,
            Import.source_candidate_id == Candidate.candidate_id,
            Import.task_id == Task.task_id,
        )
        .correlate(Attempt, Candidate, Task)
        .exists()
    )
    rejected = Candidate.disposition.in_(("rejected", "discarded"))
    pending = and_(
        Attempt.status == "success",
        Review.receipt_id.is_(None),
        Attempt.invalidated_at.is_(None),
        ~func.coalesce(rejected, False),
        func.length(Attempt.output_content) > 0,
    )
    pipeline = case(
        (Attempt.status.in_(("failed", "error")), "failed"),
        (Attempt.status == "canceled", "canceled"),
        (rejected, "rejected"),
        (Attempt.status.in_(("pending", "queued", "claimed", "running")), "running"),
        (and_(Review.receipt_id.is_not(None), imported), "imported"),
        (Review.receipt_id.is_not(None), "import_pending"),
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
            case((rejected, "审核未通过，候选产物已丢弃"), else_=Attempt.invalidated_reason).label(
                "invalidated_reason"
            ),
            func.coalesce(func.length(Attempt.output_content), 0).label("output_length"),
            Stage.stage,
            Task.task_id,
            Task.project_id,
            Task.sprint_id,
            Task.requirement_id,
            case((Review.receipt_id.is_not(None), Candidate.candidate_id), else_=None).label(
                "candidate_id"
            ),
            Review.actor_id.label("reviewer_user_id"),
            Review.created_at.label("reviewed_at"),
            Review.comment.label("review_comment"),
        )
        .select_from(Attempt)
        .join(Stage, Stage.id == Attempt.stage_id)
        .join(Task, Task.task_id == Stage.task_id)
        .join(
            Chain, and_(Chain.task_id == Task.task_id, Chain.requirement_id == Task.requirement_id)
        )
        .outerjoin(
            Candidate,
            and_(
                Candidate.chain_id == Chain.chain_id,
                Candidate.stage_id == Stage.id,
                Candidate.current_attempt_id == Attempt.id,
            ),
        )
        .outerjoin(Review, Review.receipt_id == review_id)
        .where(Task.requirement_id != "", *task_conditions)
    )
    if task_id is not None:
        query = query.where(Task.task_id == task_id)
    filtered = query
    if pipeline_filter != "all":
        filtered = filtered.where(
            Review.receipt_id.is_not(None)
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
    ids = list(
        {row.candidate_id for row in [*rows, *([latest] if latest else [])] if row.candidate_id}
    )
    imports = (
        (
            (
                await session.execute(
                    select(
                        Import.source_candidate_id.label("candidate_id"),
                        Import.target_type,
                        Import.target_id,
                        Import.imported_at,
                    )
                    .where(Import.source_kind == "current", Import.source_candidate_id.in_(ids))
                    .order_by(Import.imported_at, Import.import_id)
                )
            ).all()
        )
        if ids
        else []
    )
    return rows, counts, int(pending_count or 0), latest, imports
