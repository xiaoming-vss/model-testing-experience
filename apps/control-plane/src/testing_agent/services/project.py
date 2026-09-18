from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from testing_agent.core.errors import AppError, ErrNotFound, ErrProjectNameAlreadyUse
from testing_agent.core.sid import new_id
from testing_agent.models.project import Project
from testing_agent.models.project_member import ProjectMember
from testing_agent.models.user import User
from testing_agent.repositories.project import ProjectRepository
from testing_agent.schemas.project import (
    CreateProjectRequest,
    ProjectResponse,
    UpdateProjectRequest,
)
from testing_agent.schemas.project_member import AddProjectMemberRequest
from testing_agent.services.common import list_payload
from testing_agent.services.project_access import (
    ProjectAction,
    allowed_actions,
    project_role,
    require_project_access,
)
from testing_agent.services.worker_authorization import revoke_executions


def dump_project(project: Project, role: str = "owner") -> dict:
    data = ProjectResponse.model_validate(project)
    data.role = role
    data.permissions = allowed_actions(role)
    return data.model_dump(by_alias=True, mode="json")


class ProjectService:
    def __init__(self, projects: ProjectRepository):
        self.projects = projects

    async def get_accessible_entity(
        self, user_id: str, project_id: str, *, action: ProjectAction = "read"
    ) -> Project:
        project = await self.projects.get_active_by_id(project_id)
        if project is None:
            raise ErrNotFound
        await require_project_access(self.projects.session, user_id, project, action)
        return project

    async def create(self, user_id: str, body: CreateProjectRequest) -> dict:
        user = await self.projects.session.scalar(
            select(User).where(User.user_id == user_id).with_for_update()
        )
        if user is None:
            raise ErrNotFound
        exists = await self.projects.get_active_by_user_and_name(user_id, body.name)
        if exists is not None:
            raise ErrProjectNameAlreadyUse
        project = Project(
            project_id=new_id(),
            user_id=user_id,
            name=body.name,
            description=body.description,
        )
        self.projects.add(project)
        await self.projects.commit()
        await self.projects.refresh(project)
        return dump_project(project)

    async def list(self, user_id: str) -> dict[str, Any]:
        rows = await self.projects.list_active_by_user(user_id)
        return list_payload(
            [
                dump_project(row, await project_role(self.projects.session, user_id, row))
                for row in rows
            ]
        )

    async def get(self, user_id: str, project_id: str) -> dict:
        project = await self.projects.get_active_by_id(project_id)
        if project is None:
            raise ErrNotFound
        role = await require_project_access(self.projects.session, user_id, project)
        return dump_project(project, role)

    async def update(self, user_id: str, project_id: str, body: UpdateProjectRequest) -> dict:
        project = await self.get_accessible_entity(user_id, project_id, action="manage")
        if body.name is not None and body.name != project.name:
            exists = await self.projects.get_active_by_user_and_name(user_id, body.name)
            if exists is not None:
                raise ErrProjectNameAlreadyUse
            project.name = body.name
        if body.description is not None:
            project.description = body.description
        await self.projects.commit()
        await self.projects.refresh(project)
        return dump_project(project)

    async def delete(self, user_id: str, project_id: str) -> dict:
        project = await self.get_accessible_entity(user_id, project_id, action="manage")
        await revoke_executions(self.projects.session, project_id=project_id)
        await self.projects.hard_delete(project)
        await self.projects.commit()
        return {}

    async def add_member(
        self, user_id: str, project_id: str, body: AddProjectMemberRequest
    ) -> dict:
        session = self.projects.session
        target = await session.scalar(
            select(User).where(User.nickname == body.name).with_for_update()
        )
        project = await self._locked_project(user_id, project_id)
        if target is None:
            raise ErrNotFound
        existing = await project_role(session, target.user_id, project)
        if existing:
            raise AppError(2006, "用户已是项目成员", 409)
        session.add(ProjectMember(project_id=project_id, user_id=target.user_id, role=body.role))
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise AppError(2006, "用户已是项目成员", 409) from exc
        return {"userId": target.user_id, "name": target.nickname, "role": body.role}

    async def list_members(self, user_id: str, project_id: str) -> dict:
        project = await self.projects.get_active_by_id(project_id)
        if project is None:
            raise ErrNotFound
        session = self.projects.session
        await require_project_access(session, user_id, project)
        owner = await session.scalar(select(User).where(User.user_id == project.user_id))
        items = []
        if owner is not None:
            items.append({"userId": owner.user_id, "name": owner.nickname, "role": "owner"})
        rows = await session.execute(
            select(User, ProjectMember.role)
            .join(ProjectMember, ProjectMember.user_id == User.user_id)
            .where(ProjectMember.project_id == project_id)
            .order_by(User.nickname)
        )
        items.extend(
            {"userId": user.user_id, "name": user.nickname, "role": role} for user, role in rows
        )
        return list_payload(items)

    async def _locked_project(
        self, user_id: str, project_id: str, *, manage: bool = True
    ) -> Project:
        session = self.projects.session
        project = await session.scalar(
            select(Project)
            .where(Project.project_id == project_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if project is None:
            raise ErrNotFound
        await require_project_access(session, user_id, project, "manage" if manage else "read")
        return project

    async def change_member(self, user_id: str, project_id: str, target_id: str, role: str) -> dict:
        project = await self._locked_project(user_id, project_id)
        if target_id == project.user_id:
            raise AppError(2007, "所有者必须通过所有权转移变更", 409)
        member = await self.projects.session.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id, ProjectMember.user_id == target_id
            )
        )
        if member is None:
            raise ErrNotFound
        member.role = role
        await self.projects.commit()
        return {}

    async def remove_member(self, user_id: str, project_id: str, target_id: str) -> dict:
        project = await self._locked_project(user_id, project_id, manage=user_id != target_id)
        if target_id == project.user_id:
            raise AppError(2007, "所有者退出前必须转移或删除项目", 409)
        member = await self.projects.session.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id, ProjectMember.user_id == target_id
            )
        )
        if member is None:
            raise ErrNotFound
        await revoke_executions(self.projects.session, actor=target_id, project_id=project_id)
        await self.projects.session.delete(member)
        await self.projects.commit()
        return {}

    async def transfer(self, user_id: str, project_id: str, target_id: str) -> dict:
        session = self.projects.session
        users = list(
            (
                await session.scalars(
                    select(User)
                    .where(User.user_id.in_((user_id, target_id)))
                    .order_by(User.user_id)
                    .with_for_update()
                )
            ).all()
        )
        target = next((user for user in users if user.user_id == target_id), None)
        project = await self._locked_project(user_id, project_id)
        member = await session.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id, ProjectMember.user_id == target_id
            )
        )
        if target is None or member is None:
            raise ErrNotFound
        # The legacy owner/name uniqueness also applies to transferred projects.
        if await self.projects.get_active_by_user_and_name(target_id, project.name) is not None:
            raise ErrProjectNameAlreadyUse
        await session.delete(member)
        await session.flush()
        session.add(ProjectMember(project_id=project_id, user_id=user_id, role="member"))
        project.user_id = target_id
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise ErrProjectNameAlreadyUse from exc
        return dump_project(project, "member")
