"""Complete-round LDAP eligibility reconciliation, coordinated by a database lease."""

import asyncio
import logging
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from testing_agent.core.config import Settings, get_settings
from testing_agent.core.ldap_directory import LdapDirectory
from testing_agent.domain.ldap_identity import DirectoryIdentity, DirectoryUnavailable
from testing_agent.repositories.auth_runtime import AuthRuntimeRepository
from testing_agent.repositories.user import UserRepository
from testing_agent.services.auth_mode import AuthModeService
from testing_agent.services.auth_session import invalidate_sessions

logger = logging.getLogger(__name__)


class ReconcileDirectory(Protocol):
    async def inspect(
        self, external_ids: tuple[str, ...]
    ) -> dict[str, DirectoryIdentity | None]: ...


@dataclass(frozen=True, slots=True)
class ReconcileAccount:
    user_id: str
    external_id: str
    status: str
    token_version: int


def utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class LdapReconciler:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        directory: ReconcileDirectory,
    ) -> None:
        self.sessions = session_factory
        self.settings = settings
        self.directory = directory

    async def run_once(self) -> int | None:
        """Return disabled count, or None when another instance holds the lease."""
        if not self.settings.ldap.enabled:
            return None
        owner = str(uuid4())
        acquired = False
        query_finished = False
        try:
            async with self.sessions() as session:
                runtime = AuthRuntimeRepository(session)
                generation = await AuthModeService(runtime, self.settings).require_current(
                    for_update=True
                )
                row = await runtime.get(for_update=True)
                assert row is not None  # require_current verified the singleton.
                now = datetime.now(UTC)
                if row.reconcile_until and utc(row.reconcile_until) > now:
                    return None
                row.reconcile_owner = owner
                row.reconcile_until = now + timedelta(
                    seconds=self.settings.ldap.login_timeout_seconds + 30
                )
                users = await UserRepository(session).list_ldap_accounts()
                if any(not user.external_id for user in users):
                    raise DirectoryUnavailable("linked_identity_missing")
                accounts = tuple(
                    ReconcileAccount(
                        user.user_id,
                        user.external_id or "",
                        user.status,
                        user.token_version,
                    )
                    for user in users
                )
                await session.commit()
                acquired = True
            # No DB transaction or row lock remains open during directory requests.
            ids = tuple(account.external_id for account in accounts)
            async with asyncio.timeout(self.settings.ldap.login_timeout_seconds):
                results = await self.directory.inspect(ids)
            query_finished = True
            if set(results) != set(ids):
                raise DirectoryUnavailable("incomplete_round")
            if any(
                value is not None and value.external_id != key for key, value in results.items()
            ):
                raise DirectoryUnavailable("identity_mismatch")
            async with self.sessions() as session:
                runtime = AuthRuntimeRepository(session)
                current = await AuthModeService(runtime, self.settings).require_current(
                    for_update=True
                )
                row = await runtime.get(for_update=True)
                assert row is not None
                now = datetime.now(UTC)
                if (
                    current != generation
                    or row.reconcile_owner != owner
                    or row.reconcile_until is None
                    or utc(row.reconcile_until) <= now
                ):
                    raise DirectoryUnavailable("stale_round")
                disabled = 0
                repository = UserRepository(session)
                for account in accounts:
                    identity = results[account.external_id]
                    if identity is not None and identity.eligible:
                        continue
                    if account.status != "active":
                        continue
                    user = await repository.get_by_user_id_for_update(account.user_id)
                    if (
                        user is None
                        or user.is_super_admin
                        or user.auth_source != "ldap"
                        or user.external_id != account.external_id
                        or user.status != "active"
                        or user.token_version != account.token_version
                    ):
                        continue
                    user.status = "disabled"
                    user.disabled_reason = "LDAP 对账禁用"
                    user.disabled_at = now
                    user.disabled_by = ""
                    invalidate_sessions(user)
                    disabled += 1
                row.reconcile_owner = ""
                row.reconcile_until = None
                await session.commit()
            logger.info(
                "LDAP reconciliation succeeded",
                extra={
                    "last_success_at": now.isoformat(),
                    "disabled_count": disabled,
                },
            )
            return disabled
        finally:
            if acquired and query_finished:
                # A canceled blocking query may still be closing its socket; its lease
                # expires naturally instead of admitting overlapping directory work.
                # Release only this round's lease; never clear a successor's lease.
                async with self.sessions() as session:
                    row = await AuthRuntimeRepository(session).get(for_update=True)
                    if row is not None and row.reconcile_owner == owner:
                        row.reconcile_owner = ""
                        row.reconcile_until = None
                        await session.commit()


async def monitor_ldap(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings | None = None,
) -> None:
    import time

    from testing_agent.services.ldap_settings import effective_settings

    bootstrap = settings or get_settings()
    last_run = time.monotonic()
    while True:
        await asyncio.sleep(5)
        try:
            async with session_factory() as session:
                current = await effective_settings(AuthRuntimeRepository(session), bootstrap)
            if not current.ldap.enabled:
                continue
            if time.monotonic() - last_run < current.ldap.reconcile_interval_seconds:
                continue
            last_run = time.monotonic()
            await LdapReconciler(session_factory, current, LdapDirectory(current.ldap)).run_once()
        except Exception as exc:
            logger.warning(
                "LDAP reconciliation failed; no successful round recorded",
                extra={
                    "error_type": type(exc).__name__,
                    "safe_stack": "".join(
                        traceback.format_list(traceback.extract_tb(exc.__traceback__))
                    ),
                },
            )
