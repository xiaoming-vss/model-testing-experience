"""Bounded visualization reads; transaction ownership remains with the service."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.case_visualization import (
    TestOrderEntryVisualization,
    TestOrderVisualizationBatch,
)
from testing_agent.models.test_order_entry import TestOrderEntry


class CaseVisualizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def entry(
        self, order_id: str, entry_id: str, *, lock: bool = False
    ) -> TestOrderEntry | None:
        statement = (
            select(TestOrderEntry)
            .where(
                TestOrderEntry.order_id == order_id,
                TestOrderEntry.entry_id == entry_id,
            )
            .execution_options(populate_existing=True)
        )
        return await self.session.scalar(statement.with_for_update() if lock else statement)

    async def binding(self, entry_id: str) -> TestOrderEntryVisualization | None:
        return await self.session.scalar(
            select(TestOrderEntryVisualization)
            .where(
                TestOrderEntryVisualization.entry_id == entry_id,
            )
            .execution_options(populate_existing=True)
        )

    async def latest(self, task_id: str) -> AiGenerationAttempt | None:
        return await self.session.scalar(
            select(AiGenerationAttempt)
            .join(
                AiGenerationStage,
                AiGenerationStage.id == AiGenerationAttempt.stage_id,
            )
            .where(AiGenerationStage.task_id == task_id)
            .order_by(
                AiGenerationAttempt.attempt_no.desc(),
                AiGenerationAttempt.id.desc(),
            )
            .limit(1)
            .execution_options(populate_existing=True)
        )

    async def attempt(self, attempt_id: str) -> AiGenerationAttempt | None:
        return await self.session.get(AiGenerationAttempt, attempt_id, populate_existing=True)

    async def task(self, task_id: str) -> AiGenerateTask | None:
        return await self.session.scalar(
            select(AiGenerateTask)
            .where(
                AiGenerateTask.task_id == task_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def batch(self, batch_id: str, order_id: str) -> TestOrderVisualizationBatch | None:
        return await self.session.scalar(
            select(TestOrderVisualizationBatch).where(
                TestOrderVisualizationBatch.batch_id == batch_id,
                TestOrderVisualizationBatch.order_id == order_id,
            )
        )

    async def batch_replay(self, actor: str, request_id: str) -> TestOrderVisualizationBatch | None:
        return await self.session.scalar(
            select(TestOrderVisualizationBatch)
            .where(
                TestOrderVisualizationBatch.actor_id == actor,
                TestOrderVisualizationBatch.request_id == request_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def run(self, task_id: str, run_id: str) -> AiGenerationAttempt | None:
        return await self.session.scalar(
            select(AiGenerationAttempt)
            .join(
                AiGenerationStage,
                AiGenerationStage.id == AiGenerationAttempt.stage_id,
            )
            .where(AiGenerationStage.task_id == task_id, AiGenerationAttempt.execution_id == run_id)
            .order_by(AiGenerationAttempt.attempt_no.desc())
            .limit(1)
        )

    async def entries(self, order_id: str, entry_ids: list[str]) -> list[TestOrderEntry]:
        return list(
            await self.session.scalars(
                select(TestOrderEntry).where(
                    TestOrderEntry.order_id == order_id,
                    TestOrderEntry.entry_id.in_(entry_ids),
                )
            )
        )

    async def bindings(self, entry_ids: list[str]) -> list[TestOrderEntryVisualization]:
        return list(
            await self.session.scalars(
                select(TestOrderEntryVisualization).where(
                    TestOrderEntryVisualization.entry_id.in_(entry_ids),
                )
            )
        )

    async def summary_attempts(
        self,
        task_ids: list[str],
        effective_ids: list[str],
        run_ids: list[str] | None = None,
    ) -> list[tuple[str, AiGenerationAttempt]]:
        from sqlalchemy import func, or_
        from sqlalchemy.orm import load_only

        ranked = (
            select(
                AiGenerationAttempt.id,
                func.row_number()
                .over(
                    partition_by=AiGenerationStage.task_id,
                    order_by=AiGenerationAttempt.attempt_no.desc(),
                )
                .label("rank"),
            )
            .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
            .where(
                AiGenerationStage.task_id.in_(task_ids),
            )
            .subquery()
        )
        newest = select(ranked.c.id).where(ranked.c.rank == 1)
        rows = await self.session.execute(
            select(AiGenerationStage.task_id, AiGenerationAttempt)
            .join(
                AiGenerationStage,
                AiGenerationStage.id == AiGenerationAttempt.stage_id,
            )
            .where(
                AiGenerationStage.task_id.in_(task_ids),
                or_(
                    AiGenerationAttempt.id.in_(newest),
                    AiGenerationAttempt.id.in_(effective_ids),
                    AiGenerationAttempt.execution_id.in_(run_ids or []),
                ),
            )
            .options(
                load_only(
                    AiGenerationAttempt.id,
                    AiGenerationAttempt.execution_id,
                    AiGenerationAttempt.status,
                    AiGenerationAttempt.attempt_no,
                    AiGenerationAttempt.output_context_json,
                    AiGenerationAttempt.error_message,
                    AiGenerationAttempt.invalidated_at,
                )
            )
        )
        return [(task_id, attempt) for task_id, attempt in rows.all()]
