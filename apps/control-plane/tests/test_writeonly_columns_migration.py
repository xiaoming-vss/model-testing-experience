"""Downgrade must preserve populated tables while restoring removed columns."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_downgrade_restores_constraints_with_multiple_existing_rows():
    path = Path(__file__).parents[1] / "alembic/versions/20261010_0038_drop_writeonly_columns.py"
    spec = importlib.util.spec_from_file_location("writeonly_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE ai_generate_stage_attempts (id VARCHAR(64) PRIMARY KEY)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE ai_generate_run_imports (id VARCHAR(64) PRIMARY KEY, "
            "run_id VARCHAR(64) NOT NULL UNIQUE)"
        )
        connection.exec_driver_sql(
            "INSERT INTO ai_generate_run_imports VALUES ('i1', 'r1'), ('i2', 'r2')"
        )
        for table, *_ in migration.DROPS:
            connection.exec_driver_sql(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)")
            connection.exec_driver_sql(f"INSERT INTO {table} VALUES (1), (2)")
        migration.op = Operations(MigrationContext.configure(connection))
        migration.downgrade()
        rows = connection.exec_driver_sql(
            "SELECT run_id, idempotency_key FROM ai_generate_run_imports ORDER BY run_id"
        ).all()
        assert [row[0] for row in rows] == ["r1", "r2"]
        assert len({row[1] for row in rows}) == 2
        assert all(row[1] for row in rows)
        constraints = sa.inspect(connection).get_unique_constraints("ai_generate_run_imports")
        assert any(c["column_names"] == ["idempotency_key"] for c in constraints)
        for table, column, _, notnull, _ in migration.DROPS:
            values = connection.exec_driver_sql(f"SELECT {column} FROM {table}").scalars().all()
            assert len(values) == 2
            if notnull:
                assert all(value is not None for value in values)
