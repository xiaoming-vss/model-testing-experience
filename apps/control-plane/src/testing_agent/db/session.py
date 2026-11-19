from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from testing_agent.core.config import get_settings

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
