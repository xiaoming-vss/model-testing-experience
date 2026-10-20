from __future__ import annotations

from sqlalchemy import select

from testing_agent.models.login_rate_limit import LoginRateLimit
from testing_agent.repositories.base import BaseRepository


class LoginRateLimitRepository(BaseRepository):
    async def get(
        self, username: str, client_ip: str, auth_method: str = "local"
    ) -> LoginRateLimit | None:
        return await self.session.scalar(
            select(LoginRateLimit).where(
                LoginRateLimit.username == username,
                LoginRateLimit.client_ip == client_ip,
                LoginRateLimit.auth_method == auth_method,
            )
        )

    async def get_for_update(
        self, username: str, client_ip: str, auth_method: str = "local"
    ) -> LoginRateLimit | None:
        return await self.session.scalar(
            select(LoginRateLimit)
            .where(
                LoginRateLimit.username == username,
                LoginRateLimit.client_ip == client_ip,
                LoginRateLimit.auth_method == auth_method,
            )
            .with_for_update()
        )

    def add(self, row: LoginRateLimit) -> None:
        self.session.add(row)

    async def delete(self, row: LoginRateLimit) -> None:
        await self.session.delete(row)
