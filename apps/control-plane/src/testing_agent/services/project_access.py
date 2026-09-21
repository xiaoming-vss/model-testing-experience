"""Project-scoped roles from the database; immutable Casbin action policy.

Membership is read for every authorization. There is no cached user/role mapping
and no second writable policy store to synchronize after removal or transfer.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

import casbin  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrForbidden, ErrNotFound
from testing_agent.models.project import Project
from testing_agent.models.project_member import ProjectMember

ProjectAction = Literal["read", "write", "execute", "review", "manage"]
ACTIONS: tuple[ProjectAction, ...] = ("read", "write", "execute", "review", "manage")


@lru_cache(maxsize=1)
def _policy():
    model = casbin.Model()
    model.load_model_from_text("""
[request_definition]
r = role, action
[policy_definition]
p = role, action
[role_definition]
g = _, _
[policy_effect]
e = some(where (p.eft == allow))
[matchers]
m = g(r.role, p.role) && r.action == p.action
""")
    enforcer = casbin.Enforcer(model)
    enforcer.add_policy("viewer", "read")
    for action in ("write", "execute", "review"):
        enforcer.add_policy("member", action)
    enforcer.add_policy("owner", "manage")
    enforcer.add_grouping_policy("member", "viewer")
    enforcer.add_grouping_policy("owner", "member")
    return enforcer


def allowed_actions(role: str) -> list[str]:
    return [action for action in ACTIONS if _policy().enforce(role, action)]


async def project_role(session: AsyncSession, user_id: str, project: Project) -> str:
    if project.user_id == user_id:
        return "owner"
    role = await session.scalar(
        select(ProjectMember.role).where(
            ProjectMember.project_id == project.project_id, ProjectMember.user_id == user_id
        )
    )
    return role or ""


async def require_project_access(
    session: AsyncSession, user_id: str, project: Project, action: ProjectAction = "read"
) -> str:
    role = await project_role(session, user_id, project)
    if not _policy().enforce(role, action):
        raise ErrForbidden
    return role


async def require_project_id(
    session: AsyncSession, user_id: str, project_id: str, action: ProjectAction = "read"
) -> Project:
    project = await session.scalar(select(Project).where(Project.project_id == project_id))
    if project is None:
        raise ErrNotFound
    await require_project_access(session, user_id, project, action)
    return project


async def require_requirement_access(
    repository, user_id: str, requirement_id: str, *, action: ProjectAction = "read"
) -> None:
    requirement = await repository.get_requirement(requirement_id)
    if requirement is None:
        raise ErrNotFound
    sprint = await repository.get_sprint(requirement.sprint_id)
    if sprint is None:
        raise ErrNotFound
    project = await repository.get_project(sprint.project_id)
    if project is None:
        raise ErrNotFound
    await require_project_access(repository.session, user_id, project, action)
