"""Anchor the test order graph task to a test order."""

import sqlalchemy as sa

from alembic import op

revision = "20260919_0014"
down_revision = "20260918_0013"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ai_generate_tasks",
        sa.Column("order_id", sa.String(64), nullable=False, server_default=""),
    )
    op.create_index("ix_ai_generate_tasks_order_id", "ai_generate_tasks", ["order_id"])


def downgrade():
    op.drop_index("ix_ai_generate_tasks_order_id", table_name="ai_generate_tasks")
    op.drop_column("ai_generate_tasks", "order_id")
