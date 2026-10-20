"""Shared preparation for initial schema migration tests; no collected cases."""

from pathlib import Path

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.compiler import compiles

from testing_agent.models import Base

ROOT = Path(__file__).parent.parents[1]


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
