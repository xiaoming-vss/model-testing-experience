from __future__ import annotations

from sqlalchemy import func, select

from testing_agent.models.api_interface import ApiInterface
from testing_agent.models.software_repository import SoftwareRepository
from testing_agent.models.ui_element import UiElementGroup
from testing_agent.repositories.base import BaseRepository


class SoftwareRepositoryRepository(BaseRepository):
    async def has_ui_element_groups(self, software_repository_id: str) -> bool:
        group_id = await self.session.scalar(
            select(UiElementGroup.id)
            .where(UiElementGroup.software_repository_id == software_repository_id)
            .limit(1)
            .with_for_update()
        )
        return group_id is not None

    async def get(self, software_repository_id: str) -> SoftwareRepository | None:
        return await self.session.scalar(
            select(SoftwareRepository).where(
                SoftwareRepository.software_repository_id == software_repository_id
            )
        )

    async def get_for_update(self, software_repository_id: str) -> SoftwareRepository | None:
        statement = (
            select(SoftwareRepository)
            .where(SoftwareRepository.software_repository_id == software_repository_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return await self.session.scalar(statement)

    async def get_many(self, software_repository_ids: list[str]) -> list[SoftwareRepository]:
        if not software_repository_ids:
            return []
        return list(
            (
                await self.session.scalars(
                    select(SoftwareRepository)
                    .where(SoftwareRepository.software_repository_id.in_(software_repository_ids))
                    .order_by(SoftwareRepository.id.asc())
                )
            ).all()
        )

    async def get_by_project_and_name(
        self,
        project_id: str,
        name: str,
        *,
        exclude_software_repository_id: str = "",
    ) -> SoftwareRepository | None:
        statement = select(SoftwareRepository).where(
            SoftwareRepository.project_id == project_id,
            SoftwareRepository.name == name,
        )
        if exclude_software_repository_id:
            statement = statement.where(
                SoftwareRepository.software_repository_id != exclude_software_repository_id
            )
        return await self.session.scalar(statement.limit(1))

    async def list_by_project(self, project_id: str) -> list[SoftwareRepository]:
        counts = (
            select(
                ApiInterface.software_repository_id.label("software_repository_id"),
                func.count(ApiInterface.id).label("interface_count"),
            )
            .group_by(ApiInterface.software_repository_id)
            .subquery()
        )
        statement = (
            select(
                SoftwareRepository,
                func.coalesce(counts.c.interface_count, 0).label("interface_count"),
            )
            .outerjoin(
                counts,
                counts.c.software_repository_id == SoftwareRepository.software_repository_id,
            )
            .where(SoftwareRepository.project_id == project_id)
            .order_by(SoftwareRepository.name.asc(), SoftwareRepository.id.asc())
        )
        rows = (await self.session.execute(statement)).all()
        repositories: list[SoftwareRepository] = []
        for repository, interface_count in rows:
            repository.interface_count = int(interface_count or 0)
            repositories.append(repository)
        return repositories

    async def count_interfaces(self, software_repository_id: str) -> int:
        return int(
            await self.session.scalar(
                select(func.count(ApiInterface.id)).where(
                    ApiInterface.software_repository_id == software_repository_id
                )
            )
            or 0
        )
