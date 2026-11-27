"""Schema descriptions stay complete and MySQL initialization preserves them."""

import re

import sqlalchemy as sa
from support.mysql_initialization import mysql  # noqa: F401

from testing_agent.models import Base

GENERIC_COMMENTS = {"名称", "标题", "数据", "状态", "描述", "类型"}
# Add (table, column) with a reason only when the owning table already supplies
# the missing business scope; prefer a specific comment instead.
GENERIC_EXCEPTIONS: set[tuple[str, str]] = set()
ENUM_COLUMN = re.compile(
    r"(?:^|_)(?:status|state|kind|type|format|mode|role|severity|priority|purpose|source|decision|disposition|action|stage)$"
)
# Not closed value sets: MIME types and HTTP status codes.
NON_ENUM_COLUMNS = {("stored_files", "content_type"), ("api_interfaces", "response_status")}


def test_model_descriptions_are_complete():
    for table in Base.metadata.tables.values():
        assert table.comment and len(table.comment) <= 2048
        assert all(column.comment and len(column.comment) <= 1024 for column in table.columns)


def test_model_descriptions_are_specific():
    for table in Base.metadata.tables.values():
        for column in table.columns:
            comment = (column.comment or "").strip()
            assert re.search(r"[\u4e00-\u9fff]", comment), (
                f"{table.name}.{column.name} comment must include Chinese meaning"
            )
            if (table.name, column.name) not in GENERIC_EXCEPTIONS:
                assert comment not in GENERIC_COMMENTS, (
                    f"{table.name}.{column.name} comment is too generic: {comment}"
                )
            if (table.name, column.name) not in NON_ENUM_COLUMNS and ENUM_COLUMN.search(
                column.name
            ):
                assert "：" in comment and comment.split("：", 1)[1].strip(), (
                    f"{table.name}.{column.name} must state its allowed values"
                )


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
