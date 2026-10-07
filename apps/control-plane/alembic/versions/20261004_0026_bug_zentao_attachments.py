"""Durable per-file uploads, without retrying remote Bug creation."""

import sqlalchemy as sa

from alembic import op

revision = "20261004_0026"
down_revision = "20261004_0025"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bug_zentao_attachments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("bug_id", sa.String(64), nullable=False),
        sa.Column("file_id", sa.String(64), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("instance_url", sa.String(512), nullable=False),
        sa.Column("remote_bug_id", sa.Integer(), nullable=False),
        sa.Column("remote_file_id", sa.Integer(), nullable=True),
        sa.Column("operation_id", sa.String(64), nullable=False),
        sa.Column("actor_user_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_message", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["bug_id"], ["bugs.bug_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("bug_id", "file_id", name="uk_bug_zentao_attachment"),
    )


def downgrade():
    op.drop_table("bug_zentao_attachments")
