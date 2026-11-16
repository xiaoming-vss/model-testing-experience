from __future__ import annotations

from collections.abc import Sequence
from typing import Any, NamedTuple

from sqlalchemy import func, select, update

from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.requirement_software_repository import (
    RequirementSoftwareRepository,
)
from testing_agent.models.software_repository import SoftwareRepository
from testing_agent.models.sprint import Sprint
from testing_agent.repositories.base import BaseRepository


class RequirementRepositoryBinding(NamedTuple):
    association: RequirementSoftwareRepository
    software_repository: SoftwareRepository


def unique_by_git_repository(
    bindings: Sequence[RequirementRepositoryBinding],
) -> list[RequirementRepositoryBinding]:
    """Keep one binding per Git repository, preserving association order."""
    seen: set[tuple[str, str]] = set()
    result: list[RequirementRepositoryBinding] = []
    for binding in bindings:
        repository = binding.software_repository
        identity = (repository.repository_instance_url, repository.repository_project_id)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(binding)
    return result


class RequirementSoftwareRepositoryRepository(BaseRepository):
    async def get_requirement(self, requirement_id: str) -> Requirement | None:
        return await self.session.scalar(
            select(Requirement).where(Requirement.requirement_id == requirement_id)
        )

    async def get_sprint(self, sprint_id: str) -> Sprint | None:
        return await self.session.scalar(select(Sprint).where(Sprint.sprint_id == sprint_id))

    async def get_project(self, project_id: str) -> Project | None:
        return await self.session.scalar(select(Project).where(Project.project_id == project_id))

    async def get(
        self, requirement_id: str, software_repository_id: str
    ) -> RequirementSoftwareRepository | None:
        return await self.session.scalar(
            select(RequirementSoftwareRepository).where(
                RequirementSoftwareRepository.requirement_id == requirement_id,
                RequirementSoftwareRepository.software_repository_id == software_repository_id,
            )
        )

    async def get_for_update(
        self, requirement_id: str, software_repository_id: str
    ) -> RequirementSoftwareRepository | None:
        statement = (
            select(RequirementSoftwareRepository)
            .where(
                RequirementSoftwareRepository.requirement_id == requirement_id,
                RequirementSoftwareRepository.software_repository_id == software_repository_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return await self.session.scalar(statement)

    async def list_for_requirement(
        self, requirement_id: str
    ) -> list[RequirementSoftwareRepository]:
        return list(
            (
                await self.session.scalars(
                    select(RequirementSoftwareRepository)
                    .where(RequirementSoftwareRepository.requirement_id == requirement_id)
                    .order_by(
                        RequirementSoftwareRepository.created_at.asc(),
                        RequirementSoftwareRepository.id.asc(),
                    )
                )
            ).all()
        )

    async def list_for_requirement_with_repository(
        self, requirement_id: str
    ) -> list[RequirementRepositoryBinding]:
        rows = (
            await self.session.execute(
                select(RequirementSoftwareRepository, SoftwareRepository)
                .join(
                    SoftwareRepository,
                    SoftwareRepository.software_repository_id
                    == RequirementSoftwareRepository.software_repository_id,
                )
                .where(RequirementSoftwareRepository.requirement_id == requirement_id)
                .order_by(
                    RequirementSoftwareRepository.created_at.asc(),
                    RequirementSoftwareRepository.id.asc(),
                )
            )
        ).all()
        return [
            RequirementRepositoryBinding(association=association, software_repository=repository)
            for association, repository in rows
        ]

    async def list_for_sprint_with_repository(
        self, sprint_id: str
    ) -> list[RequirementRepositoryBinding]:
        rows = (
            await self.session.execute(
                select(RequirementSoftwareRepository, SoftwareRepository)
                .join(
                    Requirement,
                    Requirement.requirement_id == RequirementSoftwareRepository.requirement_id,
                )
                .join(
                    SoftwareRepository,
                    SoftwareRepository.software_repository_id
                    == RequirementSoftwareRepository.software_repository_id,
                )
                .where(Requirement.sprint_id == sprint_id)
                .order_by(
                    RequirementSoftwareRepository.created_at.asc(),
                    RequirementSoftwareRepository.id.asc(),
                )
            )
        ).all()
        return [
            RequirementRepositoryBinding(association=association, software_repository=repository)
            for association, repository in rows
        ]

    async def list_code_summaries(self, requirement_ids: Sequence[str]) -> list[dict[str, Any]]:
        if not requirement_ids:
            return []
        rows = (
            await self.session.execute(
                select(
                    RequirementSoftwareRepository.requirement_id,
                    SoftwareRepository.name,
                    SoftwareRepository.repository_path,
                    RequirementSoftwareRepository.branch,
                    RequirementSoftwareRepository.baseline_branch,
                    RequirementSoftwareRepository.created_at,
                )
                .join(
                    SoftwareRepository,
                    SoftwareRepository.software_repository_id
                    == RequirementSoftwareRepository.software_repository_id,
                )
                .where(RequirementSoftwareRepository.requirement_id.in_(requirement_ids))
                .order_by(
                    RequirementSoftwareRepository.created_at.asc(),
                    RequirementSoftwareRepository.id.asc(),
                )
            )
        ).all()
        return [
            {
                "requirement_id": requirement_id,
                "repository": repository_path or name,
                "branch": branch,
                "baseline_branch": baseline_branch,
            }
            for requirement_id, name, repository_path, branch, baseline_branch, _created_at in rows
        ]

    async def count_for_repository(self, software_repository_id: str) -> int:
        return int(
            await self.session.scalar(
                select(func.count(RequirementSoftwareRepository.id)).where(
                    RequirementSoftwareRepository.software_repository_id == software_repository_id
                )
            )
            or 0
        )

    async def clear_branches_for_repository(self, software_repository_id: str) -> int:
        result = await self.session.execute(
            update(RequirementSoftwareRepository)
            .where(RequirementSoftwareRepository.software_repository_id == software_repository_id)
            .values(branch="", baseline_branch="")
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def delete(self, association: RequirementSoftwareRepository) -> None:
        await self.session.delete(association)
