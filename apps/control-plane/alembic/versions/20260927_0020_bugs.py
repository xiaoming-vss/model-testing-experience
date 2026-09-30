"""Bugs and their activity records for in-platform bug management."""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision = "20260927_0020"
down_revision = "20260927_0019"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bugs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("bug_id", sa.String(64), nullable=False),
        sa.Column("bug_no", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description_html", mysql.LONGTEXT(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("reporter_user_id", sa.String(64), nullable=False),
        sa.Column("assignee_user_id", sa.String(64), nullable=False),
        sa.Column("found_sprint_id", sa.String(64), nullable=False),
        sa.Column("planned_fix_sprint_id", sa.String(64), nullable=False),
        sa.Column("requirement_id", sa.String(64), nullable=False),
        sa.Column("source_order_id", sa.String(64), nullable=False),
        sa.Column("source_entry_id", sa.String(64), nullable=False),
        sa.Column("source_case_id", sa.String(64), nullable=False),
        sa.Column("source_order_name", sa.String(100), nullable=False),
        sa.Column("source_case_title", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("bug_id", name=op.f("uq_bugs_bug_id")),
        sa.UniqueConstraint("project_id", "bug_no", name="uk_bugs_project_bug_no"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_bugs_project_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_bugs_project_id", "bugs", ["project_id"])
    op.create_index("ix_bugs_status", "bugs", ["status"])
    op.create_index("ix_bugs_found_sprint_id", "bugs", ["found_sprint_id"])
    op.create_index("ix_bugs_source_entry_id", "bugs", ["source_entry_id"])
    op.create_table(
        "bug_activities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("activity_id", sa.String(64), nullable=False),
        sa.Column("bug_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("actor_user_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=False),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("detail_json", mysql.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("activity_id", name=op.f("uq_bug_activities_activity_id")),
        sa.ForeignKeyConstraint(
            ["bug_id"],
            ["bugs.bug_id"],
            name="fk_bug_activities_bug_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_bug_activities_bug_id", "bug_activities", ["bug_id"])


def downgrade():
    op.drop_table("bug_activities")
    op.drop_table("bugs")
