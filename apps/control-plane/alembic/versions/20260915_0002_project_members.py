"""Project membership. Ownership remains in projects.user_id."""

import sqlalchemy as sa

from alembic import op

revision = "20260915_0002"
down_revision = "20260915_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_project_members"),
        sa.UniqueConstraint("project_id", "user_id", name="uk_project_member"),
        sa.CheckConstraint("role IN ('member', 'viewer')", name="project_member_role"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_project_members_user_project", "project_members", ["user_id", "project_id"])


def downgrade() -> None:
    op.drop_table("project_members")
