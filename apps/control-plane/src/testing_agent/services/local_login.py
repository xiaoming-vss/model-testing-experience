"""Local password authentication, account locking and login throttling."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from testing_agent.core.config import Settings
from testing_agent.core.enums import AccountStatus, AuthSource
from testing_agent.core.errors import (
    ErrAccountDisabled,
    ErrAccountLocked,
    ErrLdapPending,
    ErrLocalLoginRestricted,
    ErrUnauthorized,
)
from testing_agent.core.security import verify_password
from testing_agent.core.utc import as_utc
from testing_agent.models.login_rate_limit import LoginRateLimit
from testing_agent.repositories.login_rate_limit import LoginRateLimitRepository
from testing_agent.repositories.user import UserRepository
from testing_agent.schemas.auth import LoginRequest
from testing_agent.services.auth_mode import AuthModeService
from testing_agent.services.auth_session import issue_session
from testing_agent.services.login_throttle import LoginThrottle


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
        self.throttle = LoginThrottle(rate_limits, settings.login_security)
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
            locked_until = as_utc(getattr(user, "locked_until", None))
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
                    user.locked_until = now + self.throttle.lock_duration
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
        # Keep the stored row even when its window expired: the failure path resets
        # that row, and inserting a second row violates the identity unique key.
        self.throttle.active(row, now)
        return row

    async def _record_rate_limit_failure(
        self, row: LoginRateLimit | None, username: str, client_ip: str, now: datetime
    ) -> None:
        if self.rate_limits is None or not client_ip:
            return
        self.throttle.record_failure(
            row,
            username=username,
            client_ip=client_ip,
            auth_method="local",
            now=now,
        )

    async def _clear_rate_limit(self, row: LoginRateLimit | None) -> None:
        await self.throttle.clear(row)
