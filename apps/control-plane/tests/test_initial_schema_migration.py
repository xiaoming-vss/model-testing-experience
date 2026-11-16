"""The single pre-release baseline must create the current schema from an empty DB."""

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


def test_single_pre_release_baseline():
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    revisions = list(script.walk_revisions())
    # Until the first release, schema changes edit the baseline directly; there
    # must be exactly one revision and no additive update chain.
    assert len(revisions) == 1
    baseline = revisions[0]
    assert baseline.down_revision is None
    assert baseline.revision == "20261103_0001"
    source = Path(baseline.path).read_text()
    assert "testing_agent.models" not in source
    assert "create_all" not in source


def test_empty_database_initialization_and_roundtrip():
    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        config = migration_config(connection)
        command.upgrade(config, "head")
        assert_current_schema(connection)
        assert connection.execute(sa.text("SELECT id, mode FROM auth_runtime")).one() == (
            1,
            "local",
        )
        command.downgrade(config, "base")
        assert sa.inspect(connection).get_table_names() == ["alembic_version"]
        command.upgrade(config, "head")
        assert_current_schema(connection)
    engine.dispose()
