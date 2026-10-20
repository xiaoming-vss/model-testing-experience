"""Explicit authentication cutover; startup never resets existing sessions."""

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import case, update

from testing_agent.core.config import Settings
from testing_agent.core.errors import AppError, ErrLdapCutoverRequired
from testing_agent.models.auth_runtime import AuthRuntime
from testing_agent.models.user import User
from testing_agent.repositories.auth_runtime import AuthRuntimeRepository
from testing_agent.repositories.user import UserRepository


def ldap_fingerprint(settings: Settings) -> str:
    if not settings.ldap.enabled:
        return ""
    values = asdict(settings.ldap)
    if not values.get("tls_ca_pem"):
        values.pop("tls_ca_pem", None)  # Preserve fingerprints created before inline CA support.
    serialized = json.dumps(values, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


class AuthModeService:
    def __init__(self, runtime: AuthRuntimeRepository, settings: Settings) -> None:
        self.runtime = runtime
        self.settings = settings

    async def require_current(self, *, for_update: bool = False) -> int:
        row = await self.runtime.get(for_update=for_update)
        mode = "ldap" if self.settings.ldap.enabled else "local"
        # Missing row is a deployment/schema error; never silently claim a cutover succeeded.
        if row is None or row.mode != mode or row.fingerprint != ldap_fingerprint(self.settings):
            raise ErrLdapCutoverRequired()
        return row.generation

    async def switch(self) -> bool:
        """Caller stops ordinary traffic on all instances before applying target config.

        Lock ordering: runtime singleton, then user rows. Login commits must follow
        the same order. A config-only update increments generation but does not
        revoke sessions a second time; a local->LDAP transition always revokes.
        """
        session = self.runtime.session
        try:
            row = await self.runtime.get(for_update=True)
            if row is None:
                raise ErrLdapCutoverRequired()
            if row.ldap_config is not None:
                raise AppError(1032, "LDAP 已由管理员页面接管，请在页面中修改配置", 409)
            changed = await self.apply_locked(row)
            await session.commit()
            return changed
        except Exception:
            await session.rollback()
            raise

    async def apply_locked(self, row: AuthRuntime) -> bool:
        """Apply to an already locked runtime row; caller owns commit/rollback."""
        session = self.runtime.session
        mode = "ldap" if self.settings.ldap.enabled else "local"
        fingerprint = ldap_fingerprint(self.settings)
        if row.mode == mode and row.fingerprint == fingerprint:
            return False
        if mode == "ldap":
            admin = await UserRepository(session).get_super_admin()
            if admin is None or admin.must_change_password or not admin.password:
                raise ErrLdapCutoverRequired()
            if row.mode != "ldap":
                # Atomic cutover transaction: preserve disabled metadata and submitted work.
                await session.execute(
                    update(User)
                    .where(User.is_super_admin.is_(False))
                    .values(
                        token_version=User.token_version + 1,
                        status=case(
                            (
                                (User.auth_source == "local")
                                & User.external_id.is_(None)
                                & (User.status == "active"),
                                "pending_ldap",
                            ),
                            else_=User.status,
                        ),
                    )
                )
        row.mode = mode
        row.fingerprint = fingerprint
        row.generation += 1
        row.changed_at = datetime.now(UTC)
        row.reconcile_owner = ""
        row.reconcile_until = None
        return True
