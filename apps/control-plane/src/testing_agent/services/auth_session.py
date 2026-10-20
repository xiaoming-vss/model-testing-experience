"""Browser session lifecycle, shared by local and LDAP authentication."""

from datetime import UTC, datetime

from testing_agent.core.config import Settings
from testing_agent.core.enums import AccountStatus
from testing_agent.core.errors import ErrPasswordChangeRequired, ErrUnauthorized
from testing_agent.core.security import (
    access_token_hash,
    create_access_token,
    parse_access_token_claims,
)
from testing_agent.models.user import User
from testing_agent.repositories.auth_session import AuthSessionRepository
from testing_agent.schemas.auth import LoginResponse

_MUST_CHANGE_PASSWORD_ALLOWED = frozenset(
    {("GET", "/v1/user"), ("PUT", "/v1/user/password"), ("POST", "/v1/logout")}
)


def issue_session(user: User, settings: Settings, *, ldap: bool = False) -> LoginResponse:
    """Issue only after authentication has committed; keep each login's distinct jti."""
    expire_hours = (
        settings.ldap.token_expire_hours
        if ldap
        else settings.jwt_super_admin_expire_hours
        if user.is_super_admin
        else settings.jwt_user_expire_hours
    )
    return LoginResponse(
        access_token=create_access_token(
            user.user_id,
            settings,
            token_version=int(user.token_version or 0),
            expire_hours=expire_hours,
        ),
        must_change_password=False if ldap else bool(user.must_change_password),
    )


def invalidate_sessions(user: User) -> None:
    """Invalidate all sessions in the caller's account transaction; never commit here."""
    user.token_version = int(user.token_version or 0) + 1


class SessionService:
    def __init__(self, repository: AuthSessionRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    async def authenticate(self, token: str, *, method: str, path: str) -> str:
        claims = parse_access_token_claims(token, self.settings)
        account = await self.repository.account_for_token(claims.user_id, access_token_hash(token))
        if account is None or account.status != AccountStatus.ACTIVE:
            raise ErrUnauthorized()
        if account.token_version != claims.token_version:
            raise ErrUnauthorized()
        if account.must_change_password and (method, path) not in _MUST_CHANGE_PASSWORD_ALLOWED:
            raise ErrPasswordChangeRequired()
        return account.user_id

    async def logout(self, user_id: str, token: str) -> None:
        claims = parse_access_token_claims(token, self.settings)
        if claims.user_id != user_id:
            raise ErrUnauthorized()
        # Serialize concurrent revocations on the same user, as before the extraction.
        if await self.repository.lock_user(user_id) is None:
            raise ErrUnauthorized()
        await self.repository.revoke_token(
            user_id, access_token_hash(token), claims.expires_at, datetime.now(UTC)
        )
        await self.repository.commit()
