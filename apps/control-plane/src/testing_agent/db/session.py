from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from testing_agent.core.config import Settings, get_settings

_settings = get_settings()
if not _settings.database_url.strip():
    raise RuntimeError(
        "data.db.user.dsn is required; run `python3 scripts/manage.py configure --mode local` "
        "or set the DSN in config/platform.toml"
    )
_database_url = _settings.database_url
_pool_options = (
    {}
    if _database_url.startswith("sqlite")
    else {
        "pool_size": _settings.db_pool_size,
        "max_overflow": _settings.db_max_overflow,
    }
)
_engine = create_async_engine(_database_url, pool_pre_ping=True, **_pool_options)
AsyncSessionLocal = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


def create_engine(settings: Settings) -> AsyncEngine:
    """Build an engine for an explicit configuration, used by operational CLIs."""
    options = (
        {}
        if settings.database_url.startswith("sqlite")
        else {
            "pool_size": settings.db_pool_size,
            "max_overflow": settings.db_max_overflow,
        }
    )
    return create_async_engine(settings.database_url, pool_pre_ping=True, **options)


def create_sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
