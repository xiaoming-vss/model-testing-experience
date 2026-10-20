"""Create the single system super administrator during process startup."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from testing_agent.core.config import Settings
from testing_agent.core.security import hash_password
from testing_agent.core.sid import new_id
from testing_agent.domain.account_policy import normalize_email
from testing_agent.models.user import User


async def seed_super_admin(settings: Settings) -> None:
    """Create the configured super admin once; never overwrite an existing one."""
    config = settings.super_admin
    if not config.configured:
        raise RuntimeError(
            "security.super_admin.username and security.super_admin.email are required"
        )
    if not settings.database_url:
        raise RuntimeError("A database DSN is required to initialize the super administrator")
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            try:
                await _seed(session, settings)
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(
                    select(User.user_id).where(User.is_super_admin.is_(True))
                )
                if existing is None:
                    raise
    finally:
        await engine.dispose()


def _initial_password(configured: str) -> str:
    if configured.strip() and configured != "GENERATE":
        return configured
    return "mtx123456"


async def _seed(session, settings: Settings) -> None:
    config = settings.super_admin
    username = config.username.strip()
    email = normalize_email(config.email)
    existing = await session.scalar(
        select(User).where(User.is_super_admin.is_(True)).with_for_update()
    )
    if existing is not None:
        if existing.super_admin_slot is None:
            existing.super_admin_slot = 1
            await session.commit()
        return
    by_name = await session.scalar(select(User).where(User.nickname == username))
    if by_name is not None:
        raise RuntimeError(
            "security.super_admin.username is already used by a normal account; "
            "choose another username"
        )
    by_email = await session.scalar(select(User).where(User.email == email))
    if by_email is not None:
        raise RuntimeError(
            "security.super_admin.email is already used by another account; choose another email"
        )
    now = datetime.now(UTC)
    session.add(
        User(
            user_id=new_id(),
            nickname=username,
            password=await asyncio.to_thread(
                hash_password, _initial_password(config.initial_password)
            ),
            email=email,
            is_super_admin=True,
            super_admin_slot=1,
            status="active",
            must_change_password=True,
            password_updated_at=now,
            token_version=0,
            failed_login_count=0,
        )
    )
    await session.commit()
