from __future__ import annotations

from sqlalchemy import delete, select

from testing_agent.core.errors import (
    AppError,
    ErrEmailAlreadyUse,
    ErrForbidden,
    ErrNameAlreadyUse,
    ErrNotFound,
    ErrUnauthorized,
)
from testing_agent.core.security import create_access_token, hash_password, verify_password
from testing_agent.core.sid import new_id
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.project import Project
from testing_agent.models.project_member import ProjectMember
from testing_agent.models.user import User
from testing_agent.repositories.user import UserRepository
from testing_agent.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    UpdateProfileRequest,
    UserResponse,
)
from testing_agent.services.worker_authorization import revoke_executions


class AuthService:
    def __init__(self, users: UserRepository):
        self.users = users

    async def register(self, body: RegisterRequest) -> dict:
        exists = await self.users.get_by_name(body.name)
        if exists is not None:
            raise ErrNameAlreadyUse
        if body.email:
            email_user = await self.users.get_by_email(body.email)
            if email_user is not None:
                raise ErrEmailAlreadyUse
        user = User(
            user_id=new_id(),
            nickname=body.name,
            password=hash_password(body.password),
            email=body.email or None,
        )
        self.users.add(user)
        await self.users.commit()
        await self.users.refresh(user)
        return self._user_data(user)

    async def login(self, body: LoginRequest) -> dict:
        user = await self.users.get_by_name(body.name)
        if user is None or not verify_password(body.password, user.password):
            raise ErrUnauthorized
        data = LoginResponse(access_token=create_access_token(user.user_id))
        return data.model_dump(by_alias=True)

    async def get_profile(self, user_id: str) -> dict:
        user = await self.users.get_by_user_id(user_id)
        if user is None:
            raise ErrNotFound
        return self._user_data(user)

    async def update_profile(self, user_id: str, body: UpdateProfileRequest) -> dict:
        user = await self.users.get_by_user_id(user_id)
        if user is None:
            raise ErrForbidden
        if body.name is not None and body.name != user.nickname:
            exists = await self.users.get_by_name(body.name)
            if exists is not None:
                raise ErrNameAlreadyUse
            user.nickname = body.name
        if body.email is not None:
            new_email = body.email or None
            if new_email != user.email:
                email_user = await self.users.get_by_email(new_email) if new_email else None
                if email_user is not None and email_user.user_id != user.user_id:
                    raise ErrEmailAlreadyUse
                user.email = new_email
        await self.users.commit()
        await self.users.refresh(user)
        return self._user_data(user)

    async def delete_user(self, user_id: str) -> dict:
        user = await self.users.get_by_user_id(user_id)
        if user is None:
            raise ErrForbidden
        session = self.users.session
        await session.scalar(select(User).where(User.user_id == user_id).with_for_update())
        owned = await session.scalar(
            select(Project.project_id)
            .where(Project.user_id == user_id)
            .with_for_update()
        )
        if owned is not None:
            raise AppError(2007, "请先转移或删除所有拥有的项目", 409)
        await revoke_executions(session, actor=user_id)
        await session.execute(delete(ProjectMember).where(ProjectMember.user_id == user_id))
        connections = await session.scalars(
            select(IntegrationConnection).where(IntegrationConnection.user_id == user_id)
        )
        for connection in connections:
            await self.users.hard_delete(connection)
        await self.users.delete(user)
        await self.users.commit()
        return {}

    def _user_data(self, user: User) -> dict:
        return UserResponse(
            user_id=user.user_id,
            name=user.nickname,
            email=user.email,
        ).model_dump(by_alias=True)
