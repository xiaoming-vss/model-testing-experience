"""Atomic LDAP JIT/link/profile persistence after external authentication.

This service owns its transaction. No directory IO occurs while holding user locks.
The pre-authentication snapshot prevents an in-flight bind from undoing revocation.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from testing_agent.core.enums import AccountStatus, AuthSource
from testing_agent.core.errors import (
    AppError,
    ErrAccountDisabled,
    ErrAccountLocked,
    ErrLdapConflict,
    ErrLdapCutoverRequired,
    ErrUnauthorized,
)
from testing_agent.core.sid import new_id
from testing_agent.domain.ldap_identity import DirectoryIdentity
from testing_agent.models.user import User
from testing_agent.repositories.user import UserRepository
from testing_agent.services.auth_session import invalidate_sessions


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    user_id: str
    token_version: int
    auth_source: str
    external_id: str | None


def check_ldap_account(user: User, *, allow_link: bool) -> None:
    if user.is_super_admin:
        raise ErrLdapConflict()
    if user.status == AccountStatus.DISABLED:
        raise ErrAccountDisabled()
    until = user.locked_until
    if until is not None:
        until = until if until.tzinfo else until.replace(tzinfo=UTC)
        if until > datetime.now(UTC):
            raise ErrAccountLocked()
    if user.auth_source == AuthSource.LOCAL:
        if user.external_id is not None or not allow_link:
            raise ErrLdapConflict()
        if user.status != AccountStatus.PENDING_LDAP:
            raise ErrLdapCutoverRequired()
    elif user.auth_source != AuthSource.LDAP or user.status != AccountStatus.ACTIVE:
        raise ErrLdapConflict()


class LdapAccountService:
    def __init__(self, users: UserRepository, *, auto_link: bool) -> None:
        self.users = users
        self.auto_link = auto_link

    async def snapshot(self, identity: DirectoryIdentity) -> AccountSnapshot | None:
        user = await self.users.get_by_external_id(identity.external_id)
        if user is None:
            user = await self.users.get_by_name(identity.username)
            if user is not None and user.auth_source != AuthSource.LOCAL:
                raise ErrLdapConflict()
        if user is None:
            return None
        check_ldap_account(user, allow_link=self.auto_link)
        return AccountSnapshot(user.user_id, user.token_version, user.auth_source, user.external_id)

    async def persist(
        self,
        identity: DirectoryIdentity,
        snapshot: AccountSnapshot | None,
        before_apply: Callable[[], Awaitable[None]] | None = None,
    ) -> User:
        if not identity.eligible:
            raise ErrUnauthorized()
        # Retry only uniqueness races, never repeat the external credential bind here.
        for attempt in range(2):
            try:
                if before_apply is not None:
                    await before_apply()
                user = await self._apply(identity, snapshot)
                await self.users.commit()
                return user
            except IntegrityError:
                await self.users.rollback()
                if attempt:
                    raise ErrLdapConflict() from None
                # A concurrent JIT for the SAME external identity may be resumed.
                winner = await self.users.get_by_external_id(identity.external_id)
                if winner is None or snapshot is not None:
                    await self.users.rollback()
                    raise ErrLdapConflict() from None
                await self.users.rollback()
            except Exception:
                await self.users.rollback()
                raise
        raise ErrLdapConflict()

    async def _apply(self, identity: DirectoryIdentity, snapshot: AccountSnapshot | None) -> User:
        user = await self.users.get_by_external_id(identity.external_id, for_update=True)
        if snapshot is not None:
            if user is not None and user.user_id != snapshot.user_id:
                raise ErrLdapConflict()
            if user is None:
                user = await self.users.get_by_user_id_for_update(snapshot.user_id)
            if user is None or user.token_version != snapshot.token_version:
                raise ErrUnauthorized()
            if (user.auth_source, user.external_id) != (snapshot.auth_source, snapshot.external_id):
                raise ErrLdapConflict()
        elif user is not None and user.token_version != 0:
            # A newly created identity was revoked while this login was in flight.
            raise ErrUnauthorized()
        if user is None:
            collision = await self.users.get_by_name_for_update(identity.username)
            if collision is not None:
                raise ErrLdapConflict()
        else:
            check_ldap_account(user, allow_link=self.auto_link)
        username = identity.username
        if not username or username != username.strip() or len(username) > 50:
            raise AppError(1027, "目录用户名不满足平台长度或格式要求", 400)
        emails = tuple(value.strip().lower() for value in identity.emails if value.strip())
        if len(emails) > 1:
            raise ErrLdapConflict()
        email = emails[0] if emails else (user.email if user else None)
        if (not email and user is None) or (email is not None and len(email) > 100):
            raise AppError(1027, "目录邮箱缺失或超过平台长度限制", 400)
        name_owner = await self.users.get_by_name(username)
        email_owner = await self.users.get_by_email(email) if email else None
        if any(
            owner is not None and (user is None or owner.user_id != user.user_id)
            for owner in (name_owner, email_owner)
        ):
            raise ErrLdapConflict()
        if user is None:
            user = User(
                user_id=new_id(),
                nickname=username,
                email=email,
                password="",
                auth_source=AuthSource.LDAP,
                external_id=identity.external_id,
                status=AccountStatus.ACTIVE,
                token_version=0,
                must_change_password=False,
            )
            self.users.add(user)
        elif user.auth_source == AuthSource.LOCAL:
            user.auth_source = AuthSource.LDAP
            user.external_id = identity.external_id
            user.password = ""
            user.must_change_password = False
            invalidate_sessions(user)
            user.status = AccountStatus.ACTIVE
        user.nickname = username
        user.email = email
        user.failed_login_count = 0
        user.locked_until = None
        await self.users.flush()
        return user
