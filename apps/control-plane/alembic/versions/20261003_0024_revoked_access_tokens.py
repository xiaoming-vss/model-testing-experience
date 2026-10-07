"""Persist individual access-token revocation across backend processes."""

import sqlalchemy as sa

from alembic import op

revision = "20261003_0024"
down_revision = "20261003_0023"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "revoked_access_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_revoked_access_tokens_expires_at", "revoked_access_tokens", ["expires_at"])


def downgrade():
    op.drop_table("revoked_access_tokens")
