from __future__ import annotations

from sqlalchemy import delete, func, or_, select

from testing_agent.models.login_rate_limit import LoginRateLimit
from testing_agent.models.user import User
from testing_agent.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    async def get_by_name(self, name: str) -> User | None:
        return await self.session.scalar(select(User).where(User.nickname == name))

    async def get_by_user_id(self, user_id: str) -> User | None:
        return await self.session.scalar(select(User).where(User.user_id == user_id))

    async def get_by_user_id_for_update(self, user_id: str) -> User | None:
        return await self.session.scalar(
            select(User)
            .where(User.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def list_ldap_accounts(self) -> list[User]:
        return list(
            (
                await self.session.scalars(
                    select(User)
                    .where(User.auth_source == "ldap", User.is_super_admin.is_(False))
                    .order_by(User.id)
                )
            ).all()
        )

    async def get_by_external_id(
        self, external_id: str, *, for_update: bool = False
    ) -> User | None:
        statement = select(User).where(User.auth_source == "ldap", User.external_id == external_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return await self.session.scalar(statement)

    async def get_by_name_for_update(self, name: str) -> User | None:
        return await self.session.scalar(
            select(User)
            .where(User.nickname == name)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def get_by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(User.email == email))

    async def get_super_admin(self) -> User | None:
        return await self.session.scalar(select(User).where(User.is_super_admin.is_(True)))

    async def count_super_admins(self) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).select_from(User).where(User.is_super_admin.is_(True))
            )
            or 0
        )

    async def list_admin(
        self, *, search: str = "", status: str = "", page: int = 1, page_size: int = 20
    ) -> tuple[list[User], int]:
        statement = select(User)
        if search:
            pattern = f"%{search}%"
            statement = statement.where(or_(User.nickname.like(pattern), User.email.like(pattern)))
        if status:
            statement = statement.where(User.status == status)
        total = int(
            await self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        rows = list(
            (
                await self.session.scalars(
                    statement.order_by(User.created_at.desc(), User.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        return rows, total

    async def clear_login_limits(self, username: str) -> None:
        await self.session.execute(
            delete(LoginRateLimit).where(LoginRateLimit.username == username)
        )

    async def delete(self, user: User) -> None:
        await self.session.delete(user)
