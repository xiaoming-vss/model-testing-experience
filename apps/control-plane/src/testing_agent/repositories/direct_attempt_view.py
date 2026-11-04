"""Read a requirement-chain attempt by its existing public run identity."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage


async def direct_attempt_task_id(session: AsyncSession, attempt_id: str) -> str | None:
    return await session.scalar(
        select(AiGenerateTask.task_id)
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
    version = await session.scalar(
        select(AiGenerateStageVersion).where(
            AiGenerateStageVersion.task_id == task_id,
            AiGenerateStageVersion.stage == stage.stage,
            AiGenerateStageVersion.attempt_id == attempt.id,
        )
    )
    imports = []
    if version is not None:
        imports = list(
            (
                await session.scalars(
                    select(AiGenerateVersionImport)
                    .where(
                        AiGenerateVersionImport.version_id == version.version_id,
                        AiGenerateVersionImport.task_id == task_id,
                    )
                    .order_by(AiGenerateVersionImport.imported_at, AiGenerateVersionImport.id)
                )
            ).all()
        )
    return attempt, stage, task, version, imports
