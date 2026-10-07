"""Durable manual Bug creation through the configured Zentao MCP."""

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import JSON

from alembic import op

revision = "20261003_0023"
down_revision = "20261003_0022"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "shared_services",
        sa.Column("zentao_instance_url", sa.String(512), nullable=False, server_default=""),
    )
    op.create_table(
        "bug_zentao_pushes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("bug_id", sa.String(64), nullable=False),
        sa.Column("operation_id", sa.String(64), nullable=False),
        sa.Column("actor_user_id", sa.String(64), nullable=False),
        sa.Column("service_id", sa.String(64), nullable=False),
        sa.Column("instance_url", sa.String(512), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("remote_bug_id", sa.Integer(), nullable=True),
        sa.Column("target_json", JSON(), nullable=False),
        sa.Column("payload_json", JSON(), nullable=False),
        sa.Column("error_message", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["bug_id"], ["bugs.bug_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("bug_id"),
    )


def downgrade():
    op.drop_table("bug_zentao_pushes")
    with op.batch_alter_table("shared_services") as batch:
        batch.drop_column("zentao_instance_url")
