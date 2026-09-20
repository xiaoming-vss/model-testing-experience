"""Execution is judged per case, not per step: drop the step-level result column."""

import sqlalchemy as sa

from alembic import op

revision = "20260918_0013"
down_revision = "20260918_0012"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column("test_order_entries", "step_results_json")


def downgrade():
    op.add_column("test_order_entries", sa.Column("step_results_json", sa.JSON(), nullable=True))
