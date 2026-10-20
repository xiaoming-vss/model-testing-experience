"""The frozen initial migration must create the current schema from an empty DB."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.compiler import compiles

from alembic import command
from testing_agent.models import Base

ROOT = Path(__file__).parents[1]


@compiles(LONGTEXT, "sqlite")
def compile_longtext_for_sqlite(type_, compiler, **kwargs):
    return "TEXT"


def migration_config(connection):
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.attributes["connection"] = connection
    return config


def assert_current_schema(connection):
    context = MigrationContext.configure(connection, opts={"compare_type": True})
    assert compare_metadata(context, Base.metadata) == []
    assert set(sa.inspect(connection).get_table_names()) == set(Base.metadata.tables) | {
        "alembic_version"
    }
    assert (
        context.get_current_revision()
        == ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_current_head()
    )
    # These FKs existed in development migrations and must survive the squash.
    expected = {
        "requirements": "fk_requirements_sprint",
        "api_collections": "fk_api_collections_requirement",
        "function_test_suites": "fk_function_test_suites_requirement",
        "ui_test_suites": "fk_ui_test_suites_requirement",
        "api_cases": "fk_api_cases_collection",
        "api_case_runs": "fk_api_case_runs_case",
        "api_collection_run_items": "fk_api_collection_run_items_case_run",
    }
    for table, name in expected.items():
        assert name in {fk["name"] for fk in sa.inspect(connection).get_foreign_keys(table)}


def test_one_frozen_initial_revision():
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    revisions = list(script.walk_revisions())
    initial = script.get_revision("20260915_0001")
    assert initial is not None
    assert len(revisions) >= 2
    assert initial.down_revision is None
    source = Path(initial.path).read_text()
    assert "testing_agent.models" not in source
    assert "create_all" not in source


def test_empty_database_initialization_and_roundtrip():
    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        config = migration_config(connection)
        command.upgrade(config, "head")
        assert_current_schema(connection)
        for table in ("shared_services", "service_authorizations"):
            assert (
                connection.scalar(
                    sa.select(sa.func.count()).select_from(Base.metadata.tables[table])
                )
                == 0
            )
        command.upgrade(config, "head")
        assert_current_schema(connection)
        for table in ("shared_services", "service_authorizations"):
            assert (
                connection.scalar(
                    sa.select(sa.func.count()).select_from(Base.metadata.tables[table])
                )
                == 0
            )
        command.downgrade(config, "base")
        assert sa.inspect(connection).get_table_names() == ["alembic_version"]
        command.upgrade(config, "head")
        assert_current_schema(connection)
        for table in ("shared_services", "service_authorizations"):
            assert (
                connection.scalar(
                    sa.select(sa.func.count()).select_from(Base.metadata.tables[table])
                )
                == 0
            )
    engine.dispose()


def test_developer_migration_preserves_members_and_refuses_unsafe_downgrade():
    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        config = migration_config(connection)
        command.upgrade(config, "20260927_0021")
        meta = sa.MetaData()
        meta.reflect(bind=connection)
        now = datetime.now(UTC)
        connection.execute(
            meta.tables["users"].insert(),
            {
                "user_id": "dev",
                "nickname": "dev",
                "password": "",
                "created_at": now,
                "updated_at": now,
            },
        )
        connection.execute(
            meta.tables["projects"].insert(),
            {
                "project_id": "p",
                "user_id": "dev",
                "name": "p",
                "description": "",
                "created_at": now,
                "updated_at": now,
            },
        )
        members = Base.metadata.tables["project_members"]
        connection.execute(
            members.insert(),
            {
                "project_id": "p",
                "user_id": "dev",
                "role": "member",
                "created_at": now,
            },
        )
        connection.commit()
        command.upgrade(config, "head")
        assert connection.scalar(sa.select(members.c.role)) == "member"
        connection.execute(members.update().values(role="developer"))
        connection.commit()
        with pytest.raises(RuntimeError, match="开发成员"):
            command.downgrade(config, "20260927_0021")
        connection.rollback()
        assert connection.scalar(sa.select(members.c.role)) == "developer"
        connection.execute(members.update().values(role="viewer"))
        connection.commit()
        command.downgrade(config, "20260927_0021")
        assert connection.scalar(sa.select(members.c.role)) == "viewer"
        command.upgrade(config, "head")
        assert_current_schema(connection)
    engine.dispose()
