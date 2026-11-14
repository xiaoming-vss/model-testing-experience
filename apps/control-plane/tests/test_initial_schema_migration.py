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


def test_frozen_baseline_and_additive_revisions():
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    revisions = list(script.walk_revisions())
    baseline = next(revision for revision in revisions if revision.down_revision is None)
    assert baseline.revision == "20261103_0001"
    source = Path(baseline.path).read_text()
    assert "testing_agent.models" not in source
    assert "create_all" not in source
    # The baseline stays frozen; later schema changes are additive revisions.
    assert all(
        revision.down_revision for revision in revisions if revision.revision != baseline.revision
    )


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
