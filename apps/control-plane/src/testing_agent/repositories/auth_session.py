"""Session persistence. Mutations are committed by the calling service."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select

from testing_agent.core.enums import AccountStatus
from testing_agent.models.revoked_access_token import RevokedAccessToken
from testing_agent.models.user import User
from testing_agent.repositories.base import BaseRepository


@dataclass(frozen=True)
class SessionAccount:
    user_id: str
    status: str
    token_version: int
    must_change_password: bool


class AuthSessionRepository(BaseRepository):
    async def account_for_token(self, user_id: str, token_hash: str) -> SessionAccount | None:
        revoked = (
            select(RevokedAccessToken.token_hash)
            .where(RevokedAccessToken.token_hash == token_hash)
            .exists()
        )
        row = (
            await self.session.execute(
                select(
                    User.user_id, User.status, User.token_version, User.must_change_password
                ).where(User.user_id == user_id, ~revoked)
            )
        ).first()
        if row is None:
            return None
        return SessionAccount(
            row[0], row[1] or AccountStatus.ACTIVE, int(row[2] or 0), bool(row[3])
        )

    async def lock_user(self, user_id: str) -> User | None:
        return await self.session.scalar(
            select(User).where(User.user_id == user_id).with_for_update()
        )

    async def revoke_token(
        self, user_id: str, token_hash: str, expires_at: datetime, now: datetime
    ) -> None:
        await self.session.execute(
            delete(RevokedAccessToken).where(RevokedAccessToken.expires_at <= now)
        )
        if await self.session.get(RevokedAccessToken, token_hash) is None:
            self.session.add(
                RevokedAccessToken(token_hash=token_hash, user_id=user_id, expires_at=expires_at)
            )
