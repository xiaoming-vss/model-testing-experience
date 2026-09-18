"""Attach marked environment secrets to their personal owner."""

import sqlalchemy as sa

from alembic import op

revision = "20260915_0003"
down_revision = "20260915_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "api_environment_vars",
        sa.Column("secret_user_id", sa.String(64), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("api_environment_vars", "secret_user_id")
