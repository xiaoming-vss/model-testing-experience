"""Real MySQL locks and concurrency; only an explicitly disposable *_test DB."""

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_ldap_cutover import ldap_settings
from test_mysql_initialization import mysql  # noqa: F401

from testing_agent.core.errors import AppError
from testing_agent.domain.ldap_identity import DirectoryIdentity
from testing_agent.models.login_rate_limit import LoginRateLimit
from testing_agent.models.user import User
from testing_agent.repositories.auth_runtime import AuthRuntimeRepository
from testing_agent.repositories.login_rate_limit import LoginRateLimitRepository
from testing_agent.repositories.user import UserRepository
from testing_agent.services.auth_mode import AuthModeService
from testing_agent.services.ldap_login import LdapLoginService

IDENTITY = DirectoryIdentity(
    "550e8400-e29b-41d4-a716-446655440020",
    "concurrent",
    "uid=concurrent,dc=test",
    ("concurrent@example.test",),
    True,
    True,
)


@pytest.fixture
async def database(mysql):  # noqa: F811
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    settings = ldap_settings()
    async with sessions() as session:
        session.add(
            User(
                user_id="ldap-test-admin",
                nickname="ldap-test-admin",
                password="test-hash",
                status="active",
                is_super_admin=True,
                auth_source="local",
            )
        )
        await session.commit()
        await AuthModeService(AuthRuntimeRepository(session), settings).switch()
    try:
        yield sessions, settings
    finally:
        async with sessions() as session:
            await session.execute(delete(LoginRateLimit))
            await session.execute(delete(User))
            row = await AuthRuntimeRepository(session).get(for_update=True)
            row.mode = "local"
            row.fingerprint = ""
            await session.commit()
        await engine.dispose()


def login_service(session, settings, directory):
    return LdapLoginService(
        UserRepository(session),
        LoginRateLimitRepository(session),
        AuthModeService(AuthRuntimeRepository(session), settings),
        settings,
        directory,
    )


async def test_parallel_jit_creates_one_identity_on_mysql(database):
    sessions, settings = database
    entered = 0
    all_entered = asyncio.Event()

    async def bind(*_):
        nonlocal entered
        entered += 1
        if entered == 8:
            all_entered.set()
        await asyncio.wait_for(all_entered.wait(), timeout=10)

    directory = AsyncMock()
    directory.lookup.return_value = IDENTITY
    directory.verify_password.side_effect = bind

    async def attempt():
        async with sessions() as session:
            from testing_agent.schemas.auth import LoginRequest

            return await login_service(session, settings, directory).login(
                LoginRequest(name=IDENTITY.username, password="right"), "127.0.0.1"
            )

    results = await asyncio.gather(*(attempt() for _ in range(8)))
    assert all(result["accessToken"] for result in results)
    async with sessions() as session:
        rows = (await session.scalars(select(User).where(User.auth_source == "ldap"))).all()
        assert len(rows) == 1 and rows[0].external_id == IDENTITY.external_id


async def test_revocation_during_bind_rejects_mysql_commit(database):
    from testing_agent.schemas.auth import LoginRequest

    sessions, settings = database
    async with sessions() as session:
        session.add(
            User(
                user_id="known",
                nickname=IDENTITY.username,
                password="",
                auth_source="ldap",
                external_id=IDENTITY.external_id,
                status="active",
                token_version=0,
            )
        )
        await session.commit()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def bind(*_):
        entered.set()
        await release.wait()

    directory = AsyncMock()
    directory.lookup.return_value = replace(IDENTITY, username="renamed")
    directory.verify_password.side_effect = bind

    async def attempt():
        async with sessions() as session:
            return await login_service(session, settings, directory).login(
                LoginRequest(name="renamed", password="right"), "127.0.0.1"
            )

    task = asyncio.create_task(attempt())
    try:
        await asyncio.wait_for(entered.wait(), 10)
        async with sessions() as session:
            user = await UserRepository(session).get_by_user_id_for_update("known")
            user.token_version += 1
            await session.commit()
        release.set()
        with pytest.raises(AppError) as error:
            await task
        assert error.value.http_code == 401
        async with sessions() as session:
            user = await UserRepository(session).get_by_user_id("known")
            assert user.token_version == 1 and user.nickname == IDENTITY.username
    finally:
        release.set()
        if not task.done():
            await task
