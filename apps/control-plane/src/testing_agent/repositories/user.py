from __future__ import annotations

from sqlalchemy import select

from testing_agent.models.user import User
from testing_agent.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    async def get_by_name(self, name: str) -> User | None:
        return await self.session.scalar(select(User).where(User.nickname == name))

    async def get_by_user_id(self, user_id: str) -> User | None:
        return await self.session.scalar(select(User).where(User.user_id == user_id))

    async def get_by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(User.email == email))

    async def delete(self, user: User) -> None:
        await self.session.delete(user)
