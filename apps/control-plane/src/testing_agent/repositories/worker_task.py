from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from testing_agent.models.ai_generate_task import AiGenerateTaskRun
from testing_agent.models.ai_generate_task_source_archive import AiGenerateTaskSourceArchive
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.api_collection_run import ApiCollectionRun, ApiCollectionRunItem
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.project_skill_space import ProjectSkillSpace
from testing_agent.models.requirement import Requirement
from testing_agent.models.ui_test_suite_run import UiTestSuiteRunItem
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.base import BaseRepository


class WorkerTaskRepository(BaseRepository):
    async def commit(self) -> None:
        from testing_agent.services.ai_execution import persist

        await self.session.run_sync(persist)
        await self.session.commit()

    async def _project_run(self, row):
        from testing_agent.services.ai_execution import project

        return await self.session.run_sync(lambda session: project(session, row))

    async def get_worker_task(self, domain: str, task_id: str) -> WorkerTask | None:
        row = await self.session.scalar(
            select(WorkerTask).where(
                WorkerTask.domain == domain,
                WorkerTask.task_id == task_id,
            )
        )

        return await self._hydrate(row)

    async def _hydrate(self, row):
        from testing_agent.services.worker_context import hydrate

        return await self.session.run_sync(lambda session: hydrate(session, row))

    async def expired_tasks(self, domain: str):
        return list(
            (
                await self.session.scalars(
                    select(WorkerTask)
                    .where(
                        WorkerTask.domain == domain,
                        WorkerTask.status.in_(["claimed", "running"]),
                        WorkerTask.lease_expires_at <= datetime.now(UTC),
                    )
                    .order_by(WorkerTask.id)
                    .limit(100)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )

    async def claim_pending(self, domain: str) -> WorkerTask | None:
        row = await self.session.scalar(
            select(WorkerTask)
            .where(WorkerTask.domain == domain, WorkerTask.status == "pending")
            .order_by(WorkerTask.created_at.asc(), WorkerTask.id.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )

        return await self._hydrate(row)

    async def get_api_item(self, item_id: str) -> ApiCollectionRunItem | None:
        return await self.session.scalar(
            select(ApiCollectionRunItem).where(ApiCollectionRunItem.item_id == item_id)
        )

    async def get_api_collection_run(self, collection_run_id: str) -> ApiCollectionRun | None:
        return await self.session.scalar(
            select(ApiCollectionRun).where(ApiCollectionRun.collection_run_id == collection_run_id)
        )

    async def get_api_run(self, run_id: str) -> ApiCaseRun | None:
        return await self.session.scalar(select(ApiCaseRun).where(ApiCaseRun.run_id == run_id))

    def add(self, row: ApiCaseRun) -> None:
        self.session.add(row)

    async def get_ui_item(self, item_id: str) -> UiTestSuiteRunItem | None:
        return await self.session.scalar(
            select(UiTestSuiteRunItem).where(UiTestSuiteRunItem.item_id == item_id)
        )

    async def list_project_skills(self, project_id: str) -> list[ProjectSkillSpace]:
        return list(
            (
                await self.session.scalars(
                    select(ProjectSkillSpace)
                    .where(
                        ProjectSkillSpace.project_id == project_id,
                    )
                    .order_by(
                        ProjectSkillSpace.is_default.desc(),
                        ProjectSkillSpace.created_at.desc(),
                    )
                )
            ).all()
        )

    async def get_llm_connection(self, connection_id: str) -> IntegrationConnection | None:
        return await self.session.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.connection_id == connection_id,
                IntegrationConnection.provider == "llm",
            )
        )

    async def get_ai_run(self, run_id: str) -> AiGenerateTaskRun | None:
        row = await self.session.scalar(
            select(AiGenerateTaskRun).where(AiGenerateTaskRun.run_id == run_id).with_for_update()
        )
        return await self._project_run(row)

    async def get_source_archive(self, task_id: str) -> AiGenerateTaskSourceArchive | None:
        return await self.session.scalar(
            select(AiGenerateTaskSourceArchive).where(
                AiGenerateTaskSourceArchive.task_id == task_id
            )
        )

    async def get_requirement(self, requirement_id: str) -> Requirement | None:
        return await self.session.scalar(
            select(Requirement).where(
                Requirement.requirement_id == requirement_id,
            )
        )

    async def refresh(self, row: object) -> None:
        await self.session.refresh(row)
