"""Local password authentication, account locking and login throttling."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from testing_agent.core.config import Settings
from testing_agent.core.enums import AccountStatus, AuthSource
from testing_agent.core.errors import (
    ErrAccountDisabled,
    ErrAccountLocked,
    ErrLdapPending,
    ErrLocalLoginRestricted,
    ErrTooManyLoginAttempts,
    ErrUnauthorized,
)
from testing_agent.core.security import verify_password
from testing_agent.models.login_rate_limit import LoginRateLimit
from testing_agent.repositories.login_rate_limit import LoginRateLimitRepository
from testing_agent.repositories.user import UserRepository
from testing_agent.schemas.auth import LoginRequest
from testing_agent.services.auth_mode import AuthModeService
from testing_agent.services.auth_session import issue_session


class LocalLoginService:
    def __init__(
        self,
        users: UserRepository,
        rate_limits: LoginRateLimitRepository | None,
        settings: Settings,
        mode: AuthModeService | None = None,
    ) -> None:
        self.users = users
        self.rate_limits = rate_limits
        self.settings = settings
        self.mode = mode

    async def login(self, body: LoginRequest, client_ip: str = "") -> dict:
        name = body.name.strip()
        now = datetime.now(UTC)
        user = await self.users.get_by_name(name)
        if self.mode is not None:
            if user is None or not user.is_super_admin:
                await self.mode.require_current(for_update=True)
            if user is not None:
                user = await self.users.get_by_user_id_for_update(user.user_id)
        if user is not None:
            if (user.status or AccountStatus.ACTIVE) == AccountStatus.DISABLED:
                raise ErrAccountDisabled()
            if (user.status or AccountStatus.ACTIVE) == AccountStatus.PENDING_LDAP:
                raise ErrLdapPending()
            if getattr(user, "auth_source", AuthSource.LOCAL) == AuthSource.LDAP:
                raise ErrLocalLoginRestricted()
            if self.settings.ldap.enabled and not getattr(user, "is_super_admin", False):
                raise ErrLocalLoginRestricted()
            locked_until = _aware(getattr(user, "locked_until", None))
            if locked_until is not None and locked_until > now:
                raise ErrAccountLocked()
            if locked_until is not None:
                user.failed_login_count = 0
                user.locked_until = None
        limiter_row = await self._check_rate_limit(name, client_ip, now)
        valid = await asyncio.to_thread(
            verify_password,
            body.password,
            user.password if user is not None else "",
        )
        if user is None or not valid:
            if user is not None:
                user.failed_login_count = int(getattr(user, "failed_login_count", 0) or 0) + 1
                if user.failed_login_count >= self.settings.login_security.max_failures:
                    user.locked_until = now + timedelta(
                        minutes=self.settings.login_security.lock_minutes
                    )
            await self._record_rate_limit_failure(limiter_row, name, client_ip, now)
            await self.users.commit()
            if user is not None and getattr(user, "locked_until", None) is not None:
                raise ErrAccountLocked()
            raise ErrUnauthorized()
        user.failed_login_count = 0
        user.locked_until = None
        await self._clear_rate_limit(limiter_row)
        await self.users.commit()
        return issue_session(user, self.settings).model_dump(by_alias=True)

    async def _check_rate_limit(
        self, username: str, client_ip: str, now: datetime
    ) -> LoginRateLimit | None:
        if self.rate_limits is None or not client_ip:
            return None
        row = await self.rate_limits.get_for_update(username, client_ip)
        if row is None:
            return None
        blocked_until = _aware(row.blocked_until)
        if blocked_until is not None and blocked_until > now:
            raise ErrTooManyLoginAttempts()
        window = timedelta(minutes=self.settings.login_security.rate_limit_window_minutes)
        window_started_at = _aware(row.window_started_at)
        if window_started_at is not None and window_started_at + window <= now:
            await self.rate_limits.delete(row)
            return None
        return row

    async def _record_rate_limit_failure(
        self, row: LoginRateLimit | None, username: str, client_ip: str, now: datetime
    ) -> None:
        if self.rate_limits is None or not client_ip:
            return
        window = timedelta(minutes=self.settings.login_security.rate_limit_window_minutes)
        if row is None:
            row = LoginRateLimit(
                username=username,
                client_ip=client_ip,
                attempt_count=0,
                window_started_at=now,
                blocked_until=None,
            )
            self.rate_limits.add(row)
        row.attempt_count = int(row.attempt_count or 0) + 1
        if row.attempt_count >= self.settings.login_security.max_failures:
            row.blocked_until = now + window

    async def _clear_rate_limit(self, row: LoginRateLimit | None) -> None:
        if row is not None and self.rate_limits is not None:
            await self.rate_limits.delete(row)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
