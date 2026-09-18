"""Column removal preserves business data and refuses uncleaned tombstones."""

from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from test_initial_schema_migration import assert_current_schema, migration_config

from alembic import command
from testing_agent.models import Base


def seed_project(connection, deleted=False):
    connection.execute(
        sa.text(
            "INSERT INTO projects "
            "(project_id,user_id,name,description,created_at,updated_at,deleted_at) "
            "VALUES ('keep','owner','preserved','',:now,:now,:deleted)"
        ),
        {"now": datetime.now(UTC), "deleted": datetime.now(UTC) if deleted else None},
    )
    connection.commit()


def test_upgrade_and_downgrade_preserve_business_rows():
    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        config = migration_config(connection)
        command.upgrade(config, "20260917_0008")
        seed_project(connection)
        command.upgrade(config, "head")
        assert_current_schema(connection)
        for name in Base.metadata.tables:
            assert "deleted_at" not in {c["name"] for c in sa.inspect(connection).get_columns(name)}
        assert (
            connection.scalar(sa.text("SELECT name FROM projects WHERE project_id='keep'"))
            == "preserved"
        )
        command.downgrade(config, "20260917_0008")
        assert connection.execute(
            sa.text("SELECT name, deleted_at FROM projects WHERE project_id='keep'")
        ).one() == ("preserved", None)
        command.upgrade(config, "head")
        assert_current_schema(connection)
    engine.dispose()


def test_tombstone_guard_runs_before_any_schema_change():
    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        config = migration_config(connection)
        command.upgrade(config, "20260917_0008")
        seed_project(connection, deleted=True)
        with pytest.raises(RuntimeError, match="projects still contains soft-deleted records"):
            command.upgrade(config, "head")
        assert (
            connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == "20260917_0008"
        )
        assert "deleted_at" in {
            c["name"] for c in sa.inspect(connection).get_columns("ai_generate_tasks")
        }
        assert (
            connection.scalar(sa.text("SELECT name FROM projects WHERE project_id='keep'"))
            == "preserved"
        )
    engine.dispose()
