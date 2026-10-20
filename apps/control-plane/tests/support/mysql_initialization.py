"""Shared preparation for mysql initialization tests; no collected cases."""

import os
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
import sqlalchemy as sa

from alembic import command
from support.initial_schema_migration import migration_config
from testing_agent.models import Base


@pytest.fixture(scope="module")
def mysql():
    url = os.environ.get("CONTROL_PLANE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set CONTROL_PLANE_TEST_DATABASE_URL to an empty disposable MySQL database")
    engine = sa.create_engine(url)
    assert engine.dialect.name == "mysql"
    assert engine.url.database and engine.url.database.endswith("_test")
    with engine.connect() as connection:
        assert sa.inspect(connection).get_table_names() == [], "Test database must be empty"
        config = migration_config(connection)
        command.upgrade(config, "head")
        connection.commit()
        yield engine
        command.downgrade(config, "base")
        connection.exec_driver_sql("DROP TABLE alembic_version")
        connection.commit()
    engine.dispose()


def seed_row(connection, table, overrides=None):
    """Populate required columns and real parent rows for constraint tests."""
    values = {}
    existing = {column["name"] for column in sa.inspect(connection).get_columns(table.name)}
    for col in table.columns:
        if col.name not in existing:
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
    values.update(overrides or {})
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
