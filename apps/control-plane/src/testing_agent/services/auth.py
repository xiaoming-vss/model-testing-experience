from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from testing_agent.core.config import Settings, get_settings
from testing_agent.core.errors import (
    AppError,
    ErrBadRequest,
    ErrEmailAlreadyUse,
    ErrEmailRequired,
    ErrForbidden,
    ErrLdapReadOnly,
    ErrLdapUnavailable,
    ErrNameAlreadyUse,
    ErrNotFound,
    ErrOldPasswordInvalid,
    ErrPasswordSameAsOld,
    ErrRegistrationClosed,
    ErrUsernameImmutable,
)
from testing_agent.core.security import (
    hash_password,
    verify_password,
)
from testing_agent.core.sid import new_id
from testing_agent.domain.account_policy import normalize_email, validate_password
from testing_agent.models.user import User
from testing_agent.repositories.auth_session import AuthSessionRepository
from testing_agent.repositories.login_rate_limit import LoginRateLimitRepository
from testing_agent.repositories.user import UserRepository
from testing_agent.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    UpdateProfileRequest,
    UserResponse,
)
from testing_agent.services.auth_mode import AuthModeService
from testing_agent.services.auth_session import SessionService, invalidate_sessions
from testing_agent.services.ldap_login import LdapLoginService
from testing_agent.services.local_login import LocalLoginService


class AuthService:
    def __init__(
        self,
        users: UserRepository,
        rate_limits: LoginRateLimitRepository | None = None,
        settings: Settings | None = None,
        ldap_login: LdapLoginService | None = None,
        mode: AuthModeService | None = None,
    ) -> None:
        self.users = users
        self.rate_limits = rate_limits
        self.settings = settings or get_settings()
        self.ldap_login = ldap_login
        self.mode = mode

    async def register(self, body: RegisterRequest) -> dict:
        if self.settings.ldap.enabled:
            raise ErrRegistrationClosed()
        if self.mode is not None:
            await self.mode.require_current(for_update=True)
        name = body.name.strip()
        if not name or len(name) > 50:
            raise AppError(400, "用户名长度必须为 1..50 个字符", 400)
        email = normalize_email(body.email)
        if not email:
            raise ErrEmailRequired()
        if len(email) > 100:
            raise AppError(400, "邮箱长度不能超过 100 个字符", 400)
        validate_password(body.password)
        exists = await self.users.get_by_name(name)
        if exists is not None:
            raise ErrNameAlreadyUse()
        email_user = await self.users.get_by_email(email)
        if email_user is not None:
            raise ErrEmailAlreadyUse()
        now = datetime.now(UTC)
        user = User(
            user_id=new_id(),
            nickname=name,
            password=await asyncio.to_thread(hash_password, body.password),
            email=email,
            status="active",
            password_updated_at=now,
        )
        self.users.add(user)
        await self.users.commit()
        await self.users.refresh(user)
        return self._user_data(user)

    async def login(self, body: LoginRequest, client_ip: str = "") -> dict:
        if body.auth_method == "ldap":
            if self.ldap_login is None:
                raise ErrLdapUnavailable()
            return await self.ldap_login.login(body, client_ip)
        return await LocalLoginService(
            self.users, self.rate_limits, self.settings, self.mode
        ).login(body, client_ip)

    async def get_profile(self, user_id: str) -> dict:
        user = await self.users.get_by_user_id(user_id)
        if user is None:
            raise ErrNotFound()
        return self._user_data(user)

    async def logout(self, user_id: str, token: str) -> dict:
        await SessionService(AuthSessionRepository(self.users.session), self.settings).logout(
            user_id, token
        )
        return {}

    async def update_profile(self, user_id: str, body: UpdateProfileRequest) -> dict:
        user = await self.users.get_by_user_id(user_id)
        if user is None:
            raise ErrForbidden()
        if getattr(user, "auth_source", "local") == "ldap":
            raise ErrLdapReadOnly()
        if body.name is not None and body.name.strip() != user.nickname:
            raise ErrUsernameImmutable()
        if body.email is not None:
            new_email = normalize_email(body.email)
            if not new_email:
                raise ErrEmailRequired()
            if len(new_email) > 100:
                raise ErrBadRequest()
            if new_email != user.email:
                email_user = await self.users.get_by_email(new_email)
                if email_user is not None and email_user.user_id != user.user_id:
                    raise ErrEmailAlreadyUse()
                user.email = new_email
        await self.users.commit()
        await self.users.refresh(user)
        return self._user_data(user)

    async def change_password(self, user_id: str, body: ChangePasswordRequest) -> dict:
        user = await self.users.get_by_user_id(user_id)
        if user is None:
            raise ErrForbidden()
        if getattr(user, "auth_source", "local") == "ldap":
            raise ErrLdapReadOnly()
        valid = await asyncio.to_thread(verify_password, body.old_password, user.password)
        if not valid:
            raise ErrOldPasswordInvalid()
        validate_password(body.new_password)
        if body.new_password == body.old_password:
            raise ErrPasswordSameAsOld()
        user.password = await asyncio.to_thread(hash_password, body.new_password)
        user.password_updated_at = datetime.now(UTC)
        user.must_change_password = False
        invalidate_sessions(user)
        user.failed_login_count = 0
        user.locked_until = None
        await self.users.commit()
        return {}

    def _user_data(self, user: User) -> dict:
        return UserResponse(
            user_id=user.user_id,
            name=user.nickname,
            email=user.email,
            auth_source=getattr(user, "auth_source", None) or "local",
            is_super_admin=bool(getattr(user, "is_super_admin", False)),
            must_change_password=bool(getattr(user, "must_change_password", False)),
        ).model_dump(by_alias=True)
