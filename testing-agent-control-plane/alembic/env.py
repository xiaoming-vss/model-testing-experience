from logging.config import fileConfig

import testing_agent.models  # noqa: F401
from alembic import context
from testing_agent.core.config import load_settings
from testing_agent.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    # Explicit URLs and connections allow isolated migration tests without reading local secrets.
    url = config.get_main_option("sqlalchemy.url") or load_settings().database_url
    if not url:
        raise RuntimeError("Configure the database URL in APP_CONF before running Alembic")
    return url.replace("mysql+asyncmy://", "mysql+pymysql://")


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def migrate(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        migrate(connection)
        return
    from sqlalchemy import create_engine

    engine = create_engine(database_url(), pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            migrate(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
