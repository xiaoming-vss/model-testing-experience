"""Record the UI run environment and the variables it read or overwrote."""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision = "20261028_0051"
down_revision = "20261028_0050"
branch_labels = None
depends_on = None

_RUN_TABLES = (
    ("ui_test_case_runs", "ix_ui_test_case_runs_environment_id"),
    ("ui_test_suite_runs", "ix_ui_test_suite_runs_environment_id"),
)


def upgrade() -> None:
    for table, index_name in _RUN_TABLES:
        op.add_column(
            table,
            sa.Column(
                "environment_id",
                sa.String(64),
                nullable=False,
                server_default="",
                comment="运行使用的测试环境业务标识",
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "environment_name",
                sa.String(100),
                nullable=False,
                server_default="",
                comment="运行时的环境名称快照",
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "used_variables_json",
                mysql.JSON(),
                nullable=True,
                comment="本次运行实际读取的变量及来源步骤 JSON",
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "variable_writes_json",
                mysql.JSON(),
                nullable=True,
                comment="后置提取写回环境的值及旧值 JSON",
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "private_payload",
                mysql.LONGTEXT(),
                nullable=True,
                comment="使用集成密钥加密的变量取值，仅供本次运行使用",
            ),
        )
        op.create_index(index_name, table, ["environment_id"])


def downgrade() -> None:
    # Dropping these columns discards which variables each historical run used and wrote.
    for table, index_name in _RUN_TABLES:
        op.drop_index(index_name, table_name=table)
        op.drop_column(table, "private_payload")
        op.drop_column(table, "variable_writes_json")
        op.drop_column(table, "used_variables_json")
        op.drop_column(table, "environment_name")
        op.drop_column(table, "environment_id")
