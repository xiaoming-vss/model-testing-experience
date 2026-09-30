"""Distinguish unavailable defect collection from a measured zero."""

import sqlalchemy as sa

from alembic import op

revision = "20260924_0015"
down_revision = "20260919_0014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "sprint_daily_metrics",
        sa.Column("bug_metrics_collected", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade():
    op.drop_column("sprint_daily_metrics", "bug_metrics_collected")
