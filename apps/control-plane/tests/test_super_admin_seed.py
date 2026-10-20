"""The system super administrator is seeded once and never overwritten."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from testing_agent.core.config import Settings
from testing_agent.core.security import verify_password
from testing_agent.models import Base
from testing_agent.models.user import User
from testing_agent.services.super_admin import seed_super_admin


@compiles(LONGTEXT, "sqlite")
def sqlite_longtext(type_, compiler, **kwargs):
    return "TEXT"


def settings_for(
    url: str, *, username: str = "root", password: str = "initial-password"
) -> Settings:
    return Settings.from_mapping(
        {
            "env": "test",
            "http": {"host": "127.0.0.1", "port": 8000},
            "security": {
                "jwt": {"key": "test-jwt"},
                "super_admin": {
                    "username": username,
                    "email": f"{username}@example.test",
                    "initial_password": password,
                },
            },
            "data": {"db": {"user": {"dsn": url}}},
        }
    )


def test_seed_creates_one_protected_super_admin_and_is_idempotent(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'seed.db'}"
    settings = settings_for(url)

    async def run():
        engine = create_async_engine(url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        await seed_super_admin(settings)
        await seed_super_admin(settings_for(url, username="other", password="other-password"))
        async with sessions() as session:
            users = list((await session.scalars(select(User))).all())
        await engine.dispose()
        return users

    users = asyncio.run(run())
    assert len(users) == 1
    user = users[0]
    assert user.is_super_admin is True
    assert user.super_admin_slot == 1
    assert user.nickname == "root"
    assert user.email == "root@example.test"
    assert user.must_change_password is True
    assert verify_password("initial-password", user.password) is True


def test_seed_requires_configured_username_and_email():
    settings = Settings.from_mapping(
        {
            "env": "test",
            "http": {"host": "127.0.0.1", "port": 8000},
            "security": {"jwt": {"key": "test-jwt"}},
            "data": {"db": {"user": {"dsn": "sqlite+aiosqlite:///:memory:"}}},
        }
    )
    with pytest.raises(RuntimeError, match="super_admin.username"):
        asyncio.run(seed_super_admin(settings))
