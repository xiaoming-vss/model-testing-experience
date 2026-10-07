"""Schema descriptions stay complete and MySQL upgrades preserve data and definitions."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from test_initial_schema_migration import migration_config
from test_mysql_initialization import mysql, seed_row  # noqa: F401

from alembic import command
from testing_agent.models import Base

PATH = Path(__file__).parents[1] / "alembic/versions/20261007_0034_schema_comments.py"
spec = importlib.util.spec_from_file_location("schema_comments_revision", PATH)
revision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(revision)


def test_model_descriptions_are_complete():
    for table in Base.metadata.tables.values():
        assert table.comment and len(table.comment) <= 2048
        assert all(column.comment and len(column.comment) <= 1024 for column in table.columns)


def column_definitions(connection):
    # Includes exact types, defaults, charset, collation, generated expressions,
    # auto-increment and nullability, while excluding only the comments being edited.
    rows = connection.execute(
        sa.text(
            "SELECT TABLE_NAME, COLUMN_NAME, ORDINAL_POSITION, COLUMN_DEFAULT, IS_NULLABLE, "
            "DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, CHARACTER_OCTET_LENGTH, NUMERIC_PRECISION, "
            "NUMERIC_SCALE, DATETIME_PRECISION, CHARACTER_SET_NAME, COLLATION_NAME, "
            "COLUMN_TYPE, COLUMN_KEY, EXTRA, GENERATION_EXPRESSION "
            "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
            "ORDER BY TABLE_NAME, ORDINAL_POSITION"
        )
    )
    return [tuple(row) for row in rows]


def constraints(connection):
    inspector = sa.inspect(connection)
    return {
        name: (
            inspector.get_pk_constraint(name),
            inspector.get_foreign_keys(name),
            inspector.get_unique_constraints(name),
            inspector.get_indexes(name),
            inspector.get_check_constraints(name),
        )
        for name in inspector.get_table_names()
    }


def assert_mysql_comments(connection, cleared=False):
    inspector = sa.inspect(connection)
    for name, (table_comment, columns) in revision.COMMENTS.items():
        assert (inspector.get_table_comment(name)["text"] or "") == (
            "" if cleared else table_comment
        )
        actual = {
            column["name"]: column.get("comment") or "" for column in inspector.get_columns(name)
        }
        assert actual == ({name: "" for name in columns} if cleared else columns)


def test_mysql_comment_upgrade_preserves_definitions_constraints_and_rows(mysql):  # noqa: F811
    with mysql.connect() as connection:
        config = migration_config(connection)
        command.downgrade(config, revision.down_revision)
        seed_row(connection, Base.metadata.tables["users"])
        # Nondefault per-column collation and a quoted/escaped server default must
        # survive MODIFY COLUMN along with the original nullability and auto increment.
        connection.exec_driver_sql(
            "ALTER TABLE users MODIFY email VARCHAR(100) CHARACTER SET utf8mb4 "
            "COLLATE utf8mb4_bin NULL DEFAULT 'quoted''value'"
        )
        connection.commit()
        definitions, keys = column_definitions(connection), constraints(connection)
        rows = connection.execute(sa.select(Base.metadata.tables["users"])).all()

        command.upgrade(config, "head")
        assert_mysql_comments(connection)
        assert column_definitions(connection) == definitions
        assert constraints(connection) == keys
        assert connection.execute(sa.select(Base.metadata.tables["users"])).all() == rows

        # A user edit after upgrade is retained on downgrade; our own comments clear.
        command.downgrade(config, revision.down_revision)
        assert_mysql_comments(connection, cleared=True)
        assert column_definitions(connection) == definitions
        assert constraints(connection) == keys
        assert connection.execute(sa.select(Base.metadata.tables["users"])).all() == rows
        command.upgrade(config, "head")
        connection.exec_driver_sql("ALTER TABLE users COMMENT='自定义用户表说明'")
        connection.exec_driver_sql(
            "ALTER TABLE users MODIFY email VARCHAR(100) CHARACTER SET utf8mb4 "
            "COLLATE utf8mb4_bin NULL DEFAULT 'quoted''value' COMMENT '自定义邮箱说明'"
        )
        command.downgrade(config, revision.down_revision)
        inspector = sa.inspect(connection)
        assert inspector.get_table_comment("users")["text"] == "自定义用户表说明"
        assert next(c for c in inspector.get_columns("users") if c["name"] == "email")[
            "comment"
        ] == ("自定义邮箱说明")
        command.upgrade(config, "head")
        connection.execute(Base.metadata.tables["users"].delete())
        connection.commit()
