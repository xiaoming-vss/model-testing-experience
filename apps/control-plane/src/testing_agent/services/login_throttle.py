"""One failed-login window and lock rule for local and LDAP authentication."""

from __future__ import annotations

from datetime import datetime, timedelta

from testing_agent.core.config import LoginSecuritySettings
from testing_agent.core.errors import ErrTooManyLoginAttempts
from testing_agent.core.utc import as_utc
from testing_agent.models.login_rate_limit import LoginRateLimit
from testing_agent.repositories.login_rate_limit import LoginRateLimitRepository


class LoginThrottle:
    """Apply a fixed window and a block duration to per-identity/IP rows."""

    def __init__(
        self, repository: LoginRateLimitRepository | None, security: LoginSecuritySettings
    ) -> None:
        self.repository = repository
        self.security = security

    @property
    def window(self) -> timedelta:
        return timedelta(minutes=self.security.rate_limit_window_minutes)

    @property
    def lock_duration(self) -> timedelta:
        return timedelta(minutes=self.security.lock_minutes)

    def active(self, row: LoginRateLimit | None, now: datetime) -> LoginRateLimit | None:
        """Return a row still inside its window, or None when missing/expired."""
        if row is None:
            return None
        blocked_until = as_utc(row.blocked_until)
        if blocked_until is not None and blocked_until > now:
            raise ErrTooManyLoginAttempts()
        window_started_at = as_utc(row.window_started_at)
        if window_started_at is not None and window_started_at + self.window <= now:
            return None
        return row

    def record_failure(
        self,
        row: LoginRateLimit | None,
        *,
        username: str,
        client_ip: str,
        auth_method: str,
        now: datetime,
    ) -> LoginRateLimit:
        if row is None:
            row = LoginRateLimit(
                username=username,
                client_ip=client_ip,
                auth_method=auth_method,
                attempt_count=0,
                window_started_at=now,
                blocked_until=None,
            )
            if self.repository is None:
                raise ValueError("rate limit repository is required")
            self.repository.add(row)
        else:
            window_started_at = as_utc(row.window_started_at)
            if window_started_at is None or window_started_at + self.window <= now:
                row.attempt_count = 0
                row.window_started_at = now
                row.blocked_until = None
        row.attempt_count = int(row.attempt_count or 0) + 1
        if row.attempt_count >= self.security.max_failures:
            row.blocked_until = now + self.window
        return row

    async def clear(self, row: LoginRateLimit | None) -> None:
        if row is not None and self.repository is not None:
            await self.repository.delete(row)
