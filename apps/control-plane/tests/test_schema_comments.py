"""Schema descriptions stay complete and MySQL initialization preserves them."""

import sqlalchemy as sa
from support.mysql_initialization import mysql  # noqa: F401

from testing_agent.models import Base


def test_model_descriptions_are_complete():
    for table in Base.metadata.tables.values():
        assert table.comment and len(table.comment) <= 2048
        assert all(column.comment and len(column.comment) <= 1024 for column in table.columns)


def test_mysql_schema_comments_match_models(mysql):  # noqa: F811
    with mysql.connect() as connection:
        inspector = sa.inspect(connection)
        for name, table in Base.metadata.tables.items():
            assert (inspector.get_table_comment(name)["text"] or "") == table.comment
            actual = {
                column["name"]: column.get("comment") or ""
                for column in inspector.get_columns(name)
            }
            assert actual == {column.name: column.comment for column in table.columns}
