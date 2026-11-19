from __future__ import annotations

import logging
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.config import Settings, get_settings
from testing_agent.core.errors import AppError, ErrForbidden, ErrUnauthorized
from testing_agent.core.ldap_directory import LdapDirectory
from testing_agent.db.session import get_session
from testing_agent.models.user import User
from testing_agent.repositories.auth_runtime import AuthRuntimeRepository
from testing_agent.repositories.auth_session import AuthSessionRepository
from testing_agent.repositories.login_rate_limit import LoginRateLimitRepository
from testing_agent.repositories.project import ProjectRepository
from testing_agent.repositories.user import UserRepository
from testing_agent.services.auth import AuthService
from testing_agent.services.auth_mode import AuthModeService
from testing_agent.services.auth_session import SessionService
from testing_agent.services.ldap_login import LdapLoginService
from testing_agent.services.ldap_settings import LdapSettingsService, effective_settings
from testing_agent.services.user_admin import UserAdminService


async def get_access_token(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    if not authorization:
        raise ErrUnauthorized()
    return authorization.removeprefix("Bearer ").strip()


async def get_current_user_id(
    request: Request,
    token: str = Depends(get_access_token),
    session: AsyncSession = Depends(get_session),
) -> str:
    return await SessionService(AuthSessionRepository(session), get_settings()).authenticate(
        token, method=request.method, path=request.url.path
    )


async def require_super_admin(
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> str:
    is_super_admin = await session.scalar(
        select(User.is_super_admin).where(User.user_id == user_id)
    )
    if not is_super_admin:
        raise ErrForbidden()
    return user_id


def verify_worker_token(
    x_worker_token: Annotated[str | None, Header(alias="X-Worker-Token")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if (
        not settings.worker_key
        or not x_worker_token
        or not compare_digest(x_worker_token.encode(), settings.worker_key.encode())
    ):
        raise ErrUnauthorized()


def verify_integration_worker_token(
    x_worker_token: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    expected = settings.integration_worker_key
    if (
        not expected
        or not x_worker_token
        or not compare_digest(x_worker_token.encode(), expected.encode())
    ):
        logging.getLogger(__name__).warning("Integration worker authentication rejected status=401")
        raise ErrUnauthorized()


def verify_perf_worker_token(
    x_worker_token: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    expected = settings.perf_worker_key
    if (
        not expected
        or not x_worker_token
        or not compare_digest(x_worker_token.encode(), expected.encode())
    ):
        raise ErrUnauthorized()


async def get_effective_settings(session: AsyncSession = Depends(get_session)) -> Settings:
    return await effective_settings(AuthRuntimeRepository(session), get_settings())


def get_ldap_settings_service(session: AsyncSession = Depends(get_session)) -> LdapSettingsService:
    return LdapSettingsService(AuthRuntimeRepository(session), get_settings())


async def get_auth_service(session: AsyncSession = Depends(get_session)) -> AuthService:
    users = UserRepository(session)
    try:
        settings = await effective_settings(AuthRuntimeRepository(session), get_settings())
    except AppError:
        # Keep local super-admin recovery available if stored LDAP credentials cannot decrypt.
        settings = get_settings()
        return AuthService(
            users,
            LoginRateLimitRepository(session),
            settings,
            mode=AuthModeService(AuthRuntimeRepository(session), settings),
        )
    users = UserRepository(session)
    limits = LoginRateLimitRepository(session)
    ldap_login = LdapLoginService(
        users,
        limits,
        AuthModeService(AuthRuntimeRepository(session), settings),
        settings,
        LdapDirectory(settings.ldap),
    )
    return AuthService(users, limits, settings, ldap_login=ldap_login, mode=ldap_login.mode)


async def get_user_admin_service(session: AsyncSession = Depends(get_session)) -> UserAdminService:
    settings = await effective_settings(AuthRuntimeRepository(session), get_settings())
    return UserAdminService(
        UserRepository(session),
        ProjectRepository(session),
        settings,
        mode=AuthModeService(AuthRuntimeRepository(session), settings),
    )
