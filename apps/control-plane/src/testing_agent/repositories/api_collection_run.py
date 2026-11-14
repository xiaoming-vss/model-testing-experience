from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import load_only

from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.api_collection_run import ApiCollectionRun, ApiCollectionRunItem
from testing_agent.models.api_environment import ApiEnvironment
from testing_agent.models.api_environment_var import ApiEnvironmentVar
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.api_run_scope import ApiRunScopeRepositoryMixin
from testing_agent.repositories.base import BaseRepository


class ApiCollectionRunRepository(ApiRunScopeRepositoryMixin, BaseRepository):
    async def get_collection(self, collection_id: str) -> ApiCollection | None:
        return await self.session.scalar(
            select(ApiCollection).where(
                ApiCollection.collection_id == collection_id,
            )
        )

    async def get_requirement(self, requirement_id: str) -> Requirement | None:
        return await self.session.scalar(
            select(Requirement).where(
                Requirement.requirement_id == requirement_id,
            )
        )

    async def get_sprint(self, sprint_id: str) -> Sprint | None:
        return await self.session.scalar(select(Sprint).where(Sprint.sprint_id == sprint_id))

    async def get_project(self, project_id: str) -> Project | None:
        return await self.session.scalar(select(Project).where(Project.project_id == project_id))

    async def get_environment(self, environment_id: str) -> ApiEnvironment | None:
        return await self.session.scalar(
            select(ApiEnvironment)
            .where(
                ApiEnvironment.environment_id == environment_id,
            )
            # Snapshot readers may run concurrently while environment writers wait.
            .with_for_update(read=True)
        )

    async def list_environment_vars(self, environment_id: str) -> list[ApiEnvironmentVar]:
        return list(
            (
                await self.session.scalars(
                    select(ApiEnvironmentVar)
                    .where(ApiEnvironmentVar.environment_id == environment_id)
                    .order_by(ApiEnvironmentVar.created_at)
                )
            ).all()
        )

    async def list_cases(self, collection_id: str) -> list[ApiCase]:
        return list(
            (
                await self.session.scalars(
                    select(ApiCase)
                    .where(ApiCase.collection_id == collection_id)
                    .order_by(ApiCase.order_no)
                )
            ).all()
        )

    async def list_runs(self, collection_id: str) -> list[ApiCollectionRun]:
        return list(
            (
                await self.session.scalars(
                    select(ApiCollectionRun)
                    .where(ApiCollectionRun.collection_id == collection_id)
                    .order_by(ApiCollectionRun.created_at.desc(), ApiCollectionRun.id.desc())
                )
            ).all()
        )

    async def page_runs(
        self, collection_id: str, page: int, page_size: int
    ) -> tuple[list[ApiCollectionRun], int]:
        criteria = ApiCollectionRun.collection_id == collection_id
        total = await self.session.scalar(
            select(func.count()).select_from(ApiCollectionRun).where(criteria)
        )
        rows = list(
            (
                await self.session.scalars(
                    select(ApiCollectionRun)
                    .where(criteria)
                    .order_by(ApiCollectionRun.created_at.desc(), ApiCollectionRun.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        return rows, total or 0

    async def get_run(self, collection_run_id: str) -> ApiCollectionRun | None:
        return await self.session.scalar(
            select(ApiCollectionRun).where(ApiCollectionRun.collection_run_id == collection_run_id)
        )

    async def list_items(self, collection_run_id: str) -> list[ApiCollectionRunItem]:
        return list(
            (
                await self.session.scalars(
                    select(ApiCollectionRunItem)
                    .where(ApiCollectionRunItem.collection_run_id == collection_run_id)
                    .order_by(ApiCollectionRunItem.order_no)
                )
            ).all()
        )

    async def get_case(self, case_id: str) -> ApiCase | None:
        return await self.session.scalar(select(ApiCase).where(ApiCase.case_id == case_id))

    async def get_case_run(self, run_id: str) -> ApiCaseRun | None:
        return await self.session.scalar(select(ApiCaseRun).where(ApiCaseRun.run_id == run_id))

    async def report_cases(self, case_ids: list[str]) -> dict[str, ApiCase]:
        result = {}
        for offset in range(0, len(case_ids), 500):
            rows = await self.session.scalars(
                select(ApiCase)
                .options(load_only(ApiCase.case_id, ApiCase.name, raiseload=True))
                .where(ApiCase.case_id.in_(case_ids[offset : offset + 500]))
            )
            result.update({row.case_id: row for row in rows})
        return result

    async def report_case_runs(self, run_ids: list[str]) -> dict[str, ApiCaseRun]:
        result = {}
        for offset in range(0, len(run_ids), 500):
            rows = await self.session.scalars(
                select(ApiCaseRun)
                .options(
                    load_only(
                        ApiCaseRun.run_id,
                        ApiCaseRun.request_snapshot_json,
                        ApiCaseRun.response_snapshot_json,
                        ApiCaseRun.runtime_vars_json,
                        ApiCaseRun.extract_results_json,
                        ApiCaseRun.assert_results_json,
                        raiseload=True,
                    )
                )
                .where(ApiCaseRun.run_id.in_(run_ids[offset : offset + 500]))
            )
            result.update({row.run_id: row for row in rows})
        return result

    def add_all(self, rows: list[ApiCollectionRun | WorkerTask | ApiCollectionRunItem]) -> None:
        self.session.add_all(rows)

    def add(self, row: ApiCollectionRunItem) -> None:
        self.session.add(row)

    async def refresh(self, row: object) -> None:
        await self.session.refresh(row)
