"""Shared disposable MySQL database setup, sync and async; no collected cases."""

import os
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command
from support.initial_schema_migration import migration_config
from testing_agent.models import Base


def _mysql_fixture(revision):
    url = os.environ.get("CONTROL_PLANE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set CONTROL_PLANE_TEST_DATABASE_URL to an empty disposable MySQL database")
    engine = sa.create_engine(url)
    assert engine.dialect.name == "mysql"
    assert engine.url.database and engine.url.database.endswith("_test")
    with engine.connect() as connection:
        assert sa.inspect(connection).get_table_names() == [], "Test database must be empty"
        config = migration_config(connection)
        command.upgrade(config, revision)
        connection.commit()
        try:
            yield engine
        finally:
            # Keep later modules isolated even if a test or its cleanup fails.
            connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")
            for name in sa.inspect(connection).get_table_names():
                quoted = connection.dialect.identifier_preparer.quote(name)
                connection.exec_driver_sql(f"DROP TABLE {quoted}")
            connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS=1")
            connection.commit()
    engine.dispose()


@pytest.fixture(scope="module")
def mysql():
    yield from _mysql_fixture("head")


def clear_schema(sync_engine):
    """Delete every row of the disposable database, keeping only the Alembic revision."""
    with sync_engine.begin() as connection:
        connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")
        for name in sa.inspect(connection).get_table_names():
            if name != "alembic_version":
                quoted = connection.dialect.identifier_preparer.quote(name)
                connection.exec_driver_sql(f"DELETE FROM {quoted}")
        connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS=1")


@pytest.fixture(autouse=True)
def clean_schema(mysql):
    """Start every test of the module from the migrated but empty schema.

    Lets tests of one module replay the same seeded rows without sharing state.
    """
    clear_schema(mysql)
    yield


@pytest.fixture
async def sessions(mysql):
    """Session factory on the disposable database; its engine is disposed after the test."""
    engine, factory = async_sessions(mysql)
    yield factory
    await engine.dispose()


def async_sessions(sync_engine, **engine_options):
    """Async engine and session factory on the same disposable database as sync_engine.

    The caller owns the engine and must dispose it. Keyword arguments configure the engine,
    for example poolclass=NullPool when sessions are used from more than one event loop.
    """
    engine = create_async_engine(sync_engine.url.set(drivername="mysql+asyncmy"), **engine_options)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def capture_statements(engine):
    """Return the list that collects the lower-cased SQL text executed on the engine."""
    statements = []

    def record(_conn, _cursor, sql, _parameters, _context, _executemany):
        statements.append(sql.lower())

    sa.event.listen(engine.sync_engine, "before_cursor_execute", record)
    return statements


def seed_row(connection, table, overrides=None):
    """Populate required columns and real parent rows for constraint tests."""
    values = {}
    overrides = overrides or {}
    existing = {column["name"] for column in sa.inspect(connection).get_columns(table.name)}
    for col in table.columns:
        if col.name not in existing or col.name in overrides:
            continue
        if col.computed is not None or col.nullable or col.default is not None:
            continue
        if col.primary_key and isinstance(col.type, sa.Integer):
            continue
        if col.foreign_keys:
            parent = next(iter(col.foreign_keys)).column
            values[col.name] = seed_row(connection, parent.table)[parent.name]
        elif isinstance(col.type, sa.DateTime):
            values[col.name] = datetime.now(UTC)
        elif isinstance(col.type, sa.Date):
            values[col.name] = date.today()
        elif isinstance(col.type, sa.Boolean):
            values[col.name] = False
        elif isinstance(col.type, sa.Integer):
            values[col.name] = 1
        elif isinstance(col.type, sa.JSON):
            values[col.name] = {}
        else:
            values[col.name] = uuid4().hex[: min(getattr(col.type, "length", None) or 32, 32)]
    if table.name == "project_members":
        values["role"] = "member"
    if table.name == "sprints":
        values["end_time"] = values["start_time"] + timedelta(days=1)
    values.update(overrides)
    result = connection.execute(table.insert().values(**values))
    for key, value in zip(
        table.primary_key.columns.keys(), result.inserted_primary_key, strict=True
    ):
        values[key] = value
    # Return persisted defaults too; uniqueness may involve columns omitted above.
    return dict(
        connection.execute(
            sa.select(table).where(
                sa.and_(*(column == values[column.name] for column in table.primary_key.columns))
            )
        )
        .mappings()
        .one()
    )


def seed_api_interface(connection, project_id):
    """Seed a software repository and one interface for API task fixtures."""
    from testing_agent.models.api_interface import ApiInterface
    from testing_agent.models.software_repository import SoftwareRepository

    software_repository = seed_row(
        connection, SoftwareRepository.__table__, {"project_id": project_id}
    )
    return seed_row(
        connection,
        ApiInterface.__table__,
        {"software_repository_id": software_repository["software_repository_id"]},
    )


UNIQUE_TABLES = [
    table.name
    for table in Base.metadata.tables.values()
    if any(
        isinstance(c, sa.UniqueConstraint)
        and str(c.name).startswith("uk_")
        and all(not column.nullable for column in c.columns)
        for c in table.constraints
    )
]
