"""Read a requirement-chain attempt by its existing public run identity."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.models.ai_generate_import import AiGenerateImport
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationReviewReceipt,
    RequirementGenerationChain,
)


async def direct_attempt_task_id(session: AsyncSession, attempt_id: str) -> str | None:
    return await session.scalar(
        select(AiGenerateTask.task_id)
        .join(
            RequirementGenerationChain, RequirementGenerationChain.task_id == AiGenerateTask.task_id
        )
        .join(AiGenerationStage, AiGenerationStage.task_id == AiGenerateTask.task_id)
        .join(AiGenerationAttempt, AiGenerationAttempt.stage_id == AiGenerationStage.id)
        .where(AiGenerationAttempt.id == attempt_id, AiGenerateTask.requirement_id != "")
    )


async def direct_attempt_rows(session: AsyncSession, attempt_id: str, task_id: str):
    row = (
        await session.execute(
            select(AiGenerationAttempt, AiGenerationStage, AiGenerateTask)
            .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
            .join(AiGenerateTask, AiGenerateTask.task_id == AiGenerationStage.task_id)
            .join(
                RequirementGenerationChain,
                RequirementGenerationChain.task_id == AiGenerateTask.task_id,
            )
            .where(
                AiGenerationAttempt.id == attempt_id,
                AiGenerateTask.task_id == task_id,
                AiGenerateTask.requirement_id != "",
            )
        )
    ).one_or_none()
    if row is None:
        return None
    attempt, stage, task = row
    candidate = await session.scalar(
        select(AiGenerationCandidate).where(
            AiGenerationCandidate.stage_id == stage.id,
            AiGenerationCandidate.current_attempt_id == attempt.id,
        )
    )
    review = None
    imports: list[AiGenerateImport] = []
    if candidate is not None:
        review = await session.scalar(
            select(AiGenerationReviewReceipt)
            .where(
                AiGenerationReviewReceipt.stage_id == stage.id,
                AiGenerationReviewReceipt.candidate_id == candidate.candidate_id,
                AiGenerationReviewReceipt.attempt_id == attempt.id,
                AiGenerationReviewReceipt.decision == "adopted",
            )
            .order_by(
                AiGenerationReviewReceipt.created_at.desc(),
                AiGenerationReviewReceipt.receipt_id.desc(),
            )
            .limit(1)
        )
        imports = list(
            (
                await session.scalars(
                    select(AiGenerateImport)
                    .where(
                        AiGenerateImport.source_kind == "current",
                        AiGenerateImport.task_id == task_id,
                        AiGenerateImport.source_attempt_id == attempt.id,
                        AiGenerateImport.source_candidate_id == candidate.candidate_id,
                    )
                    .order_by(AiGenerateImport.imported_at, AiGenerateImport.import_id)
                )
            ).all()
        )
    return attempt, stage, task, imports, candidate, review
