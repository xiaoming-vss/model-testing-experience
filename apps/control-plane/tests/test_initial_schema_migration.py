"""The single frozen v1 baseline must create the current schema from an empty DB."""

from pathlib import Path

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


def test_single_frozen_initial_revision():
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    revisions = list(script.walk_revisions())
    assert len(revisions) == 1
    initial = revisions[0]
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
        command.downgrade(config, "base")
        assert sa.inspect(connection).get_table_names() == ["alembic_version"]
        command.upgrade(config, "head")
        assert_current_schema(connection)
    engine.dispose()
