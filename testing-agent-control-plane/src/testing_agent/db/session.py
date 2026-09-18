from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from testing_agent.core.config import get_settings

_settings = get_settings()
_engine = create_async_engine(
    _settings.database_url
    or "mysql+asyncmy://root:123456@127.0.0.1:3306/testing-agent-python?charset=utf8mb4",
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


async def dispose_engine() -> None:
    await _engine.dispose()
