"""Read models for requirement generation chains and approved stage versions."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.ai_tasks import task_type_for
from testing_agent.models.ai_generate_execution import (
    AiGenerateRunImport,
    AiGenerateRunStage,
    AiGenerateStageAttempt,
)
from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
from testing_agent.models.ai_generate_task_source_archive import AiGenerateTaskSourceArchive
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
from testing_agent.models.worker_task import WorkerTask
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

    async def ui_source_archive(self, task_id: str) -> AiGenerateTaskSourceArchive | None:
        return await self.session.scalar(
            select(AiGenerateTaskSourceArchive).where(
                AiGenerateTaskSourceArchive.task_id == task_id
            )
        )

    async def latest_run(self, task_id: str) -> AiGenerateTaskRun | None:
        return await self.session.scalar(
            select(AiGenerateTaskRun)
            .where(AiGenerateTaskRun.task_id == task_id)
            .order_by(AiGenerateTaskRun.created_at.desc(), AiGenerateTaskRun.id.desc())
            .limit(1)
        )

    async def run_for_update(self, run_id: str) -> AiGenerateTaskRun | None:
        return await self.session.scalar(
            select(AiGenerateTaskRun)
            .where(AiGenerateTaskRun.run_id == run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def stages(self, run_id: str) -> list[AiGenerateRunStage]:
        return list(
            (
                await self.session.scalars(
                    select(AiGenerateRunStage)
                    .where(AiGenerateRunStage.run_id == run_id)
                    .order_by(AiGenerateRunStage.stage_order)
                )
            ).all()
        )

    async def stage(self, run_id: str, stage: str) -> AiGenerateRunStage | None:
        return await self.session.scalar(
            select(AiGenerateRunStage).where(
                AiGenerateRunStage.run_id == run_id,
                AiGenerateRunStage.stage == stage,
            )
        )

    async def stage_for_update(self, run_id: str, stage: str) -> AiGenerateRunStage | None:
        return await self.session.scalar(
            select(AiGenerateRunStage)
            .where(
                AiGenerateRunStage.run_id == run_id,
                AiGenerateRunStage.stage == stage,
            )
            .with_for_update()
        )

    async def attempt(self, attempt_id: str | None) -> AiGenerateStageAttempt | None:
        if not attempt_id:
            return None
        return await self.session.scalar(
            select(AiGenerateStageAttempt).where(AiGenerateStageAttempt.id == attempt_id)
        )

    async def attempt_by_worker(self, worker_task_id: str) -> AiGenerateStageAttempt | None:
        return await self.session.scalar(
            select(AiGenerateStageAttempt).where(
                AiGenerateStageAttempt.worker_task_id == worker_task_id
            )
        )

    async def attempts_by_stages(
        self, stage_ids: list[str]
    ) -> dict[str, list[AiGenerateStageAttempt]]:
        result: dict[str, list[AiGenerateStageAttempt]] = {stage_id: [] for stage_id in stage_ids}
        for offset in range(0, len(stage_ids), 500):
            rows = await self.session.scalars(
                select(AiGenerateStageAttempt)
                .where(AiGenerateStageAttempt.stage_id.in_(stage_ids[offset : offset + 500]))
                .order_by(AiGenerateStageAttempt.attempt_no)
            )
            for row in rows:
                result[row.stage_id].append(row)
        return result

    async def versions(
        self, task_id: str, stage: str | None = None
    ) -> list[AiGenerateStageVersion]:
        query = select(AiGenerateStageVersion).where(AiGenerateStageVersion.task_id == task_id)
        if stage is not None:
            query = query.where(AiGenerateStageVersion.stage == stage)
        return list(
            (
                await self.session.scalars(
                    query.order_by(
                        AiGenerateStageVersion.stage,
                        AiGenerateStageVersion.version_no,
                    )
                )
            ).all()
        )

    async def version(self, task_id: str, version_id: str) -> AiGenerateStageVersion | None:
        return await self.session.scalar(
            select(AiGenerateStageVersion).where(
                AiGenerateStageVersion.task_id == task_id,
                AiGenerateStageVersion.version_id == version_id,
            )
        )

    async def version_for_attempt(
        self, task_id: str, stage: str, attempt_id: str
    ) -> AiGenerateStageVersion | None:
        return await self.session.scalar(
            select(AiGenerateStageVersion).where(
                AiGenerateStageVersion.task_id == task_id,
                AiGenerateStageVersion.stage == stage,
                AiGenerateStageVersion.attempt_id == attempt_id,
            )
        )

    async def next_version_no(self, task_id: str, stage: str) -> int:
        current = await self.session.scalar(
            select(func.max(AiGenerateStageVersion.version_no)).where(
                AiGenerateStageVersion.task_id == task_id,
                AiGenerateStageVersion.stage == stage,
            )
        )
        return int(current or 0) + 1

    async def latest_worker(self, run_id: str) -> WorkerTask | None:
        return await self.session.scalar(
            select(WorkerTask)
            .where(WorkerTask.domain == "ai", WorkerTask.run_id == run_id)
            .order_by(WorkerTask.created_at.desc(), WorkerTask.id.desc())
            .limit(1)
        )

    async def active_worker(self, run_id: str) -> WorkerTask | None:
        return await self.session.scalar(
            select(WorkerTask)
            .where(
                WorkerTask.domain == "ai",
                WorkerTask.run_id == run_id,
                WorkerTask.status.in_({"pending", "queued", "claimed", "running"}),
            )
            .order_by(WorkerTask.created_at.desc(), WorkerTask.id.desc())
            .limit(1)
        )

    async def import_for_run(self, run_id: str) -> AiGenerateRunImport | None:
        return await self.session.scalar(
            select(AiGenerateRunImport).where(AiGenerateRunImport.run_id == run_id)
        )

    async def imports_for_task(self, task_id: str) -> dict[str, AiGenerateRunImport]:
        rows = await self.session.scalars(
            select(AiGenerateRunImport)
            .join(AiGenerateTaskRun, AiGenerateTaskRun.run_id == AiGenerateRunImport.run_id)
            .where(AiGenerateTaskRun.task_id == task_id)
        )
        return {row.run_id: row for row in rows}

    async def version_imports(self, task_id: str) -> list[AiGenerateVersionImport]:
        return list(
            (
                await self.session.scalars(
                    select(AiGenerateVersionImport)
                    .where(AiGenerateVersionImport.task_id == task_id)
                    .order_by(AiGenerateVersionImport.imported_at, AiGenerateVersionImport.id)
                )
            ).all()
        )

    async def version_import(self, import_id: str) -> AiGenerateVersionImport | None:
        return await self.session.scalar(
            select(AiGenerateVersionImport).where(AiGenerateVersionImport.import_id == import_id)
        )

    async def delete_version_imports(self, version_id: str) -> None:
        rows = await self.version_imports_for_version(version_id)
        for row in rows:
            await self.session.delete(row)

    async def version_imports_for_version(self, version_id: str) -> list[AiGenerateVersionImport]:
        return list(
            (
                await self.session.scalars(
                    select(AiGenerateVersionImport).where(
                        AiGenerateVersionImport.version_id == version_id
                    )
                )
            ).all()
        )

    async def attempts_for_task(self, task_id: str) -> list[tuple[AiGenerateStageAttempt, str]]:
        rows = await self.session.execute(
            select(AiGenerateStageAttempt, AiGenerateRunStage.stage)
            .join(
                AiGenerateRunStage,
                AiGenerateRunStage.id == AiGenerateStageAttempt.stage_id,
            )
            .join(AiGenerateTaskRun, AiGenerateTaskRun.run_id == AiGenerateRunStage.run_id)
            .where(AiGenerateTaskRun.task_id == task_id)
            .order_by(AiGenerateStageAttempt.created_at, AiGenerateStageAttempt.id)
        )
        return [(attempt, stage) for attempt, stage in rows.all()]
