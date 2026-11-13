from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from testing_agent.core.config import get_settings

_settings = get_settings()
_database_url = (
    _settings.database_url
    or "mysql+asyncmy://root:123456@127.0.0.1:3306/testing-agent-python?charset=utf8mb4"
)
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
