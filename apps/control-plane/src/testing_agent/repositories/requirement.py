from __future__ import annotations

from sqlalchemy import RowMapping, func, select

from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.repositories.base import ResourceRepository


class RequirementRepository(ResourceRepository):
    model = Requirement
    id_column = "requirement_id"

    async def list_project_page(
        self, project_id: str, sprint_id: str | None, page: int, page_size: int
    ) -> tuple[int, list[RowMapping]]:
        criteria = [Sprint.project_id == project_id]
        if sprint_id is not None:
            criteria.append(Requirement.sprint_id == sprint_id)
        total = await self.session.scalar(
            select(func.count())
            .select_from(Requirement)
            .join(Sprint, Sprint.sprint_id == Requirement.sprint_id)
            .where(*criteria)
        )
        result = await self.session.execute(
            select(
                Requirement.requirement_id,
                Requirement.sprint_id,
                Requirement.name,
                Requirement.document_type,
                Requirement.document_file_id,
                Requirement.document_filename,
                Requirement.document_hash,
                Requirement.document_download_url,
                Requirement.created_at,
                Requirement.updated_at,
                Sprint.name.label("sprint_name"),
            )
            .join(Sprint, Sprint.sprint_id == Requirement.sprint_id)
            .where(*criteria)
            .order_by(Requirement.created_at.desc(), Requirement.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return total or 0, list(result.mappings().all())

    async def get_active_by_sprint_and_name(self, sprint_id: str, name: str) -> Requirement | None:
        return await self.session.scalar(
            select(Requirement).where(
                Requirement.sprint_id == sprint_id,
                Requirement.name == name,
            )
        )

    async def get_by_sprint_and_name_unscoped(
        self, sprint_id: str, name: str
    ) -> Requirement | None:
        return await self.session.scalar(
            select(Requirement).where(
                Requirement.sprint_id == sprint_id,
                Requirement.name == name,
            )
        )

    async def list_active_by_sprint(self, sprint_id: str) -> list[Requirement]:
        return list(
            (
                await self.session.scalars(
                    select(Requirement)
                    .where(Requirement.sprint_id == sprint_id)
                    .order_by(Requirement.created_at.desc())
                )
            ).all()
        )

    def add(self, requirement: Requirement) -> None:
        self.session.add(requirement)

    async def refresh(self, requirement: Requirement) -> None:
        await self.session.refresh(requirement)
