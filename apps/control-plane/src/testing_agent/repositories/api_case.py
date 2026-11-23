from __future__ import annotations

from sqlalchemy import select

from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.api_environment import ApiEnvironment
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.base import ResourceRepository


class ApiCaseRepository(ResourceRepository):
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

    async def get_execution_context(
        self, case_id: str
    ) -> tuple[ApiCase, ApiCollection, Requirement | None, Sprint | None, Project] | None:
        """Load the project and optional requirement chain for live execution."""
        row = (
            await self.session.execute(
                select(ApiCase, ApiCollection, Requirement, Sprint, Project)
                .join(ApiCollection, ApiCollection.collection_id == ApiCase.collection_id)
                .outerjoin(Requirement, Requirement.requirement_id == ApiCollection.requirement_id)
                .outerjoin(Sprint, Sprint.sprint_id == Requirement.sprint_id)
                .join(Project, Project.project_id == ApiCollection.project_id)
                .where(ApiCase.case_id == case_id)
            )
        ).one_or_none()
        return tuple(row) if row is not None else None

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

    async def list_cases(
        self, collection_id: str, *, invalidated: bool | None = None
    ) -> list[ApiCase]:
        conditions = [ApiCase.collection_id == collection_id]
        if invalidated is True:
            conditions.append(ApiCase.invalidated_at.is_not(None))
        elif invalidated is False:
            conditions.append(ApiCase.invalidated_at.is_(None))
        return list(
            (
                await self.session.scalars(
                    select(ApiCase)
                    .where(*conditions)
                    .order_by(ApiCase.order_no, ApiCase.created_at)
                )
            ).all()
        )

    async def list_project_cases_by_ids(
        self, project_id: str, case_ids: list[str]
    ) -> list[ApiCase]:
        """按项目范围加载选中用例并锁定状态列，供批量失效/恢复正常事务使用。"""
        cases: list[ApiCase] = []
        for offset in range(0, len(case_ids), 500):
            cases.extend(
                (
                    await self.session.scalars(
                        select(ApiCase)
                        .join(ApiCollection, ApiCollection.collection_id == ApiCase.collection_id)
                        .where(
                            ApiCollection.project_id == project_id,
                            ApiCase.case_id.in_(case_ids[offset : offset + 500]),
                        )
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                ).all()
            )
        return cases

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
            # Multiple submissions may snapshot the same environment together;
            # writers still wait until those snapshots have committed.
            .with_for_update(read=True)
        )

    async def get_run(self, run_id: str) -> ApiCaseRun | None:
        return await self.session.scalar(select(ApiCaseRun).where(ApiCaseRun.run_id == run_id))

    def add(self, obj: ApiCase | ApiCaseRun | WorkerTask) -> None:
        self.session.add(obj)

    def add_all(self, objs: list[ApiCaseRun | WorkerTask]) -> None:
        self.session.add_all(objs)

    async def refresh(self, obj: ApiCase | ApiCaseRun) -> None:
        await self.session.refresh(obj)
