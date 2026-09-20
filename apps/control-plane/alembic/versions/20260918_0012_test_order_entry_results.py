"""Record step-level execution results, actual results and the manual override on entries."""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision = "20260918_0012"
down_revision = "20260918_0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("test_order_entries", sa.Column("step_results_json", mysql.JSON(), nullable=True))
    op.add_column(
        "test_order_entries",
        sa.Column("actual_results", sa.String(512), nullable=False, server_default=""),
    )
    op.add_column(
        "test_order_entries",
        sa.Column("failure_reason", sa.String(512), nullable=False, server_default=""),
    )
    op.add_column(
        "test_order_entries",
        sa.Column("block_reason", sa.String(512), nullable=False, server_default=""),
    )
    op.add_column(
        "test_order_entries",
        sa.Column("zentao_bug_id", sa.String(64), nullable=False, server_default=""),
    )
    op.add_column(
        "test_order_entries",
        sa.Column("executor_user_id", sa.String(64), nullable=False, server_default=""),
    )
    op.add_column(
        "test_order_entries", sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade():
    for column in (
        "executed_at",
        "executor_user_id",
        "zentao_bug_id",
        "block_reason",
        "failure_reason",
        "actual_results",
        "step_results_json",
    ):
        op.drop_column("test_order_entries", column)
