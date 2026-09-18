"""Saved reports must not query remote data using the reader's credentials."""

import sqlalchemy as sa

from alembic import op

revision = "20260915_0005"
down_revision = "20260915_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sprint_daily_metrics", sa.Column("bug_details_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sprint_daily_metrics", "bug_details_json")
