"""Project-scoped roles from the database; immutable Casbin action policy.

Membership is read for every authorization. There is no cached user/role mapping
and no second writable policy store to synchronize after removal or transfer.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrForbidden, ErrNotFound
from testing_agent.domain.project_policy import (
    ProjectAction as ProjectAction,
)
from testing_agent.domain.project_policy import (
    allowed_actions as allowed_actions,
)
from testing_agent.domain.project_policy import (
    allows_project_action,
    effective_project_role,
)
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.repositories.project_access import ProjectAccessRepository


class RequirementAccessRepository(Protocol):
    session: AsyncSession

    async def get_requirement(self, requirement_id: str) -> Requirement | None: ...
    async def get_sprint(self, sprint_id: str) -> Sprint | None: ...
    async def get_project(self, project_id: str) -> Project | None: ...


async def is_super_admin(session: AsyncSession, user_id: str) -> bool:
    return await ProjectAccessRepository(session).is_super_admin(user_id)


async def project_role(session: AsyncSession, user_id: str, project: Project) -> str:
    repository = ProjectAccessRepository(session)
    owner = project.user_id == user_id
    admin = not owner and await repository.is_super_admin(user_id)
    member_role = (
        None if owner or admin else await repository.member_role(user_id, project.project_id)
    )
    return effective_project_role(is_owner=owner, member_role=member_role, is_super_admin=admin)


async def require_project_access(
    session: AsyncSession, user_id: str, project: Project, action: ProjectAction = "read"
) -> str:
    role = await project_role(session, user_id, project)
    if not allows_project_action(role, action):
        raise ErrForbidden()
    return role


async def require_project_id(
    session: AsyncSession, user_id: str, project_id: str, action: ProjectAction = "read"
) -> Project:
    project = await ProjectAccessRepository(session).project(project_id)
    if project is None:
        raise ErrNotFound()
    await require_project_access(session, user_id, project, action)
    return project


async def require_requirement_access(
    repository: RequirementAccessRepository,
    user_id: str,
    requirement_id: str,
    *,
    action: ProjectAction = "read",
) -> None:
    requirement = await repository.get_requirement(requirement_id)
    if requirement is None:
        raise ErrNotFound()
    sprint = await repository.get_sprint(requirement.sprint_id)
    if sprint is None:
        raise ErrNotFound()
    project = await repository.get_project(sprint.project_id)
    if project is None:
        raise ErrNotFound()
    await require_project_access(repository.session, user_id, project, action)
