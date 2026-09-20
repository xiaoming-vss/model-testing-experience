"""Assign an executor to execution entries; only the project owner may assign."""

import sqlalchemy as sa

from alembic import op

revision = "20260918_0011"
down_revision = "20260918_0010"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "test_order_entries",
        sa.Column("assignee_user_id", sa.String(64), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_test_order_entries_assignee_user_id", "test_order_entries", ["assignee_user_id"]
    )


def downgrade():
    op.drop_index("ix_test_order_entries_assignee_user_id", table_name="test_order_entries")
    op.drop_column("test_order_entries", "assignee_user_id")
