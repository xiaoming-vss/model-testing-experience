"""Read models for requirement generation chains and approved stage versions."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.ai_tasks import task_type_for
from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.repositories.requirement_design import requirement_scope


class GenerationChainRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def task(self, requirement_id: str, kind: str) -> AiGenerateTask | None:
        return await self.session.scalar(
            select(AiGenerateTask)
            .where(
                *requirement_scope(requirement_id),
                AiGenerateTask.task_type == task_type_for(kind),
            )
            .order_by(AiGenerateTask.created_at.desc(), AiGenerateTask.id.desc())
            .limit(1)
        )

    async def task_for_update(self, requirement_id: str, kind: str) -> AiGenerateTask | None:
        return await self.session.scalar(
            select(AiGenerateTask)
            .where(
                *requirement_scope(requirement_id),
                AiGenerateTask.task_type == task_type_for(kind),
            )
            .order_by(AiGenerateTask.created_at.desc(), AiGenerateTask.id.desc())
            .limit(1)
            .with_for_update()
        )

    async def latest_version(self, task_id: str, stage: str) -> AiGenerateStageVersion | None:
        return await self.session.scalar(
            select(AiGenerateStageVersion)
            .where(AiGenerateStageVersion.task_id == task_id, AiGenerateStageVersion.stage == stage)
            .order_by(AiGenerateStageVersion.version_no.desc())
            .limit(1)
        )

    async def has_stage_version(self, task_id: str, stage: str) -> bool:
        return (
            await self.session.scalar(
                select(AiGenerateStageVersion.version_id)
                .where(
                    AiGenerateStageVersion.task_id == task_id, AiGenerateStageVersion.stage == stage
                )
                .limit(1)
            )
            is not None
        )

    async def version(self, task_id: str, version_id: str) -> AiGenerateStageVersion | None:
        return await self.session.scalar(
            select(AiGenerateStageVersion).where(
                AiGenerateStageVersion.task_id == task_id,
                AiGenerateStageVersion.version_id == version_id,
            )
        )

    async def lock_versions(self, version_ids: list[str]) -> list[AiGenerateStageVersion]:
        """Lock selected inputs in a stable order before dispatch or deletion."""
        if not version_ids:
            return []
        return list(
            (
                await self.session.scalars(
                    select(AiGenerateStageVersion)
                    .where(AiGenerateStageVersion.version_id.in_(version_ids))
                    .order_by(AiGenerateStageVersion.version_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        )

    async def version_import(self, import_id: str) -> AiGenerateVersionImport | None:
        return await self.session.scalar(
            select(AiGenerateVersionImport).where(AiGenerateVersionImport.import_id == import_id)
        )

    async def version_for_stage(
        self, task_id: str, version_id: str, stage: str
    ) -> AiGenerateStageVersion | None:
        return await self.session.scalar(
            select(AiGenerateStageVersion).where(
                AiGenerateStageVersion.task_id == task_id,
                AiGenerateStageVersion.version_id == version_id,
                AiGenerateStageVersion.stage == stage,
            )
        )

    async def attempt(self, attempt_id: int | str) -> AiGenerationAttempt | None:
        return await self.session.scalar(
            select(AiGenerationAttempt).where(AiGenerationAttempt.id == attempt_id)
        )

    async def latest_requirement_analysis_task(self, requirement_id: str) -> AiGenerateTask | None:
        return await self.session.scalar(
            select(AiGenerateTask)
            .where(
                AiGenerateTask.requirement_id == requirement_id,
                AiGenerateTask.task_type == "requirement_analysis",
            )
            .order_by(AiGenerateTask.created_at.desc(), AiGenerateTask.id.desc())
            .limit(1)
        )

    async def profile_attempts(self, task_id: str) -> list[AiGenerationAttempt]:
        return list(
            (
                await self.session.scalars(
                    select(AiGenerationAttempt)
                    .join(
                        AiGenerationStage,
                        AiGenerationStage.id == AiGenerationAttempt.stage_id,
                    )
                    .where(
                        AiGenerationStage.task_id == task_id,
                        AiGenerationStage.stage == "generate",
                        AiGenerationAttempt.status == "success",
                        AiGenerationAttempt.output_content.is_not(None),
                    )
                    .order_by(
                        func.coalesce(
                            AiGenerationAttempt.finished_at, AiGenerationAttempt.created_at
                        ),
                        AiGenerationAttempt.id,
                    )
                )
            ).all()
        )
