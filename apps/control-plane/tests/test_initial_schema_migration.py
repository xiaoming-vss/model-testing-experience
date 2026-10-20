"""The frozen initial migration must create the current schema from an empty DB."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from support.initial_schema_migration import (
    ROOT as ROOT,
)
from support.initial_schema_migration import (
    assert_current_schema as assert_current_schema,
)
from support.initial_schema_migration import (
    compile_longtext_for_sqlite as compile_longtext_for_sqlite,
)
from support.initial_schema_migration import (
    migration_config as migration_config,
)

from alembic import command
from testing_agent.models import Base


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
