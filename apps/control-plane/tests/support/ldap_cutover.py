"""Shared preparation for ldap cutover tests; no collected cases."""

from dataclasses import replace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from testing_agent.core.config import Settings
from testing_agent.core.ldap_config import LdapSettings
from testing_agent.models.auth_runtime import AuthRuntime
from testing_agent.models.user import User


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(AuthRuntime.__table__.create)
        await conn.run_sync(User.__table__.create)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        session.add(AuthRuntime(id=1))
        session.add_all(
            [
                User(
                    user_id="admin",
                    nickname="root",
                    password="hash",
                    is_super_admin=True,
                    status="active",
                    auth_source="local",
                    token_version=3,
                ),
                User(
                    user_id="local",
                    nickname="local",
                    password="hash",
                    status="active",
                    token_version=2,
                ),
                User(
                    user_id="disabled",
                    nickname="disabled",
                    password="hash",
                    status="disabled",
                    disabled_reason="manual",
                    disabled_by="admin",
                    token_version=7,
                ),
                User(
                    user_id="ldap",
                    nickname="ldap",
                    password="",
                    status="active",
                    auth_source="ldap",
                    external_id="550e8400-e29b-41d4-a716-446655440000",
                    token_version=1,
                ),
            ]
        )
        await session.commit()
        yield session
    await engine.dispose()


def ldap_settings():
    return replace(
        Settings.from_mapping({}),
        ldap=LdapSettings(
            enabled=True,
            server_url="ldap://directory.test",
            bind_dn="uid=reader,dc=test",
            bind_password="test",
            user_search_base="dc=test",
            access_group_dn="cn=platform,dc=test",
        ),
    )
