"""LDAP login orchestration, with no database locks held during directory IO."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Protocol

from testing_agent.core.config import Settings
from testing_agent.core.errors import (
    ErrAccountLocked,
    ErrBadRequest,
    ErrForbidden,
    ErrLdapUnavailable,
    ErrTooManyLoginAttempts,
    ErrUnauthorized,
)
from testing_agent.domain.ldap_identity import (
    DirectoryCredentialsRejected,
    DirectoryIdentity,
    DirectoryUnavailable,
)
from testing_agent.models.login_rate_limit import LoginRateLimit
from testing_agent.repositories.login_rate_limit import LoginRateLimitRepository
from testing_agent.repositories.user import UserRepository
from testing_agent.schemas.auth import LoginRequest
from testing_agent.services.auth_mode import AuthModeService
from testing_agent.services.auth_session import issue_session
from testing_agent.services.ldap_accounts import (
    AccountSnapshot,
    LdapAccountService,
    check_ldap_account,
)


class LoginDirectory(Protocol):
    async def lookup(self, username: str) -> DirectoryIdentity | None: ...
    async def verify_password(self, identity: DirectoryIdentity, password: str) -> None: ...


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class LdapLoginService:
    def __init__(
        self,
        users: UserRepository,
        limits: LoginRateLimitRepository,
        mode: AuthModeService,
        settings: Settings,
        directory: LoginDirectory,
    ) -> None:
        self.users = users
        self.limits = limits
        self.mode = mode
        self.settings = settings
        self.directory = directory
        self.accounts = LdapAccountService(users, auto_link=settings.ldap.auto_link_by_username)

    async def login(self, body: LoginRequest, client_ip: str) -> dict:
        if not self.settings.ldap.enabled:
            raise ErrForbidden()
        name = body.name.strip()
        if not name or not body.password:
            raise ErrBadRequest()
        if len(name) > 50:
            raise ErrBadRequest()
        try:
            async with asyncio.timeout(self.settings.ldap.login_timeout_seconds):
                return await self._login(body, name, client_ip)
        except (DirectoryUnavailable, TimeoutError):
            await self.users.rollback()
            raise ErrLdapUnavailable() from None
        except BaseException:
            await self.users.rollback()
            raise

    async def _login(self, body: LoginRequest, name: str, ip: str) -> dict:
        generation = await self.mode.require_current()
        await self._limit(name, ip)
        await self.users.rollback()
        identity = await self.directory.lookup(name)
        if identity is None:
            await self._failure(name, ip, None, generation)
            raise ErrUnauthorized()
        # Canonical directory username is authoritative for account locks and success cleanup.
        snapshot = await self.accounts.snapshot(identity)
        await self._limit(identity.username, ip)
        await self.users.rollback()
        if not identity.eligible:
            raise ErrUnauthorized()
        try:
            await self.directory.verify_password(identity, body.password)
        except DirectoryCredentialsRejected:
            await self._failure(identity.username, ip, snapshot, generation)
            raise ErrUnauthorized() from None

        async def prepare_commit() -> None:
            if await self.mode.require_current(for_update=True) != generation:
                raise ErrLdapUnavailable()
            await self._limit(identity.username, ip)
            limit = await self.limits.get_for_update(identity.username, ip, "ldap")
            if limit is not None:
                await self.limits.delete(limit)

        user = await self.accounts.persist(identity, snapshot, before_apply=prepare_commit)
        return issue_session(user, self.settings, ldap=True).model_dump(by_alias=True)

    async def _limit(self, name: str, ip: str) -> LoginRateLimit | None:
        row = await self.limits.get(name, ip, "ldap")
        now = datetime.now(UTC)
        if row is not None:
            if row.blocked_until and aware(row.blocked_until) > now:
                raise ErrTooManyLoginAttempts()
            if (
                aware(row.window_started_at)
                + timedelta(minutes=self.settings.login_security.rate_limit_window_minutes)
                <= now
            ):
                return None
        return row

    async def _failure(
        self, name: str, ip: str, snapshot: AccountSnapshot | None, generation: int
    ) -> None:
        # All LDAP failure inserts serialize via runtime, including absent limiter rows.
        if await self.mode.require_current(for_update=True) != generation:
            raise ErrLdapUnavailable()
        now = datetime.now(UTC)
        user = None
        if snapshot is not None:
            user = await self.users.get_by_user_id_for_update(snapshot.user_id)
            if user is None or user.token_version != snapshot.token_version:
                raise ErrUnauthorized()
            check_ldap_account(user, allow_link=self.settings.ldap.auto_link_by_username)
            if user.locked_until is not None:
                user.failed_login_count = 0
                user.locked_until = None
            user.failed_login_count += 1
            if user.failed_login_count >= self.settings.login_security.max_failures:
                user.locked_until = now + timedelta(
                    minutes=self.settings.login_security.lock_minutes
                )
        row = await self.limits.get_for_update(name, ip, "ldap")
        if row is None:
            row = LoginRateLimit(
                auth_method="ldap",
                username=name,
                client_ip=ip,
                attempt_count=0,
                window_started_at=now,
            )
            self.limits.add(row)
        elif row.blocked_until and aware(row.blocked_until) > now:
            raise ErrTooManyLoginAttempts()
        elif (
            aware(row.window_started_at)
            + timedelta(minutes=self.settings.login_security.rate_limit_window_minutes)
            <= now
        ):
            row.attempt_count = 0
            row.window_started_at = now
            row.blocked_until = None
        row.attempt_count += 1
        if row.attempt_count >= self.settings.login_security.max_failures:
            row.blocked_until = now + timedelta(
                minutes=self.settings.login_security.rate_limit_window_minutes
            )
        locked = user is not None and user.locked_until is not None
        await self.users.commit()
        if locked:
            raise ErrAccountLocked()
