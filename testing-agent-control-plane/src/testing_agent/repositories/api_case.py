from __future__ import annotations

from sqlalchemy import select

from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.api_environment import ApiEnvironment
from testing_agent.models.api_environment_var import ApiEnvironmentVar
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.api_run_scope import ApiRunScopeRepositoryMixin
from testing_agent.repositories.base import ResourceRepository


class ApiCaseRepository(ApiRunScopeRepositoryMixin, ResourceRepository):
    model = ApiCase
    id_column = "case_id"

    async def get_collection(self, collection_id: str) -> ApiCollection | None:
        return await self.session.scalar(
            select(ApiCollection).where(
                ApiCollection.collection_id == collection_id,
            )
        )

    async def get_case(self, case_id: str) -> ApiCase | None:
        return await self.session.scalar(select(ApiCase).where(ApiCase.case_id == case_id))

    async def get_case_by_collection_and_name(
        self, collection_id: str, name: str, exclude_case_id: str | None = None
    ) -> ApiCase | None:
        stmt = select(ApiCase).where(
            ApiCase.collection_id == collection_id,
            ApiCase.name == name,
        )
        if exclude_case_id:
            stmt = stmt.where(ApiCase.case_id != exclude_case_id)
        return await self.session.scalar(stmt)

    async def list_cases(self, collection_id: str) -> list[ApiCase]:
        return list(
            (
                await self.session.scalars(
                    select(ApiCase)
                    .where(
                        ApiCase.collection_id == collection_id,
                    )
                    .order_by(ApiCase.order_no, ApiCase.created_at)
                )
            ).all()
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
            .with_for_update()
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

    async def get_run(self, run_id: str) -> ApiCaseRun | None:
        return await self.session.scalar(select(ApiCaseRun).where(ApiCaseRun.run_id == run_id))

    def add(self, obj: ApiCase | ApiCaseRun | WorkerTask) -> None:
        self.session.add(obj)

    def add_all(self, objs: list[ApiCaseRun | WorkerTask]) -> None:
        self.session.add_all(objs)

    async def refresh(self, obj: ApiCase | ApiCaseRun) -> None:
        await self.session.refresh(obj)
