"""S3 skill package references and persisted UI trace references."""

import sqlalchemy as sa

from alembic import op

revision = "20260927_0019"
down_revision = "20260927_0018"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "project_skill_spaces",
        sa.Column("file_id", sa.String(64), nullable=False, server_default=""),
    )
    for table in ("ui_test_case_runs", "ui_test_suite_runs"):
        op.add_column(
            table, sa.Column("trace_path", sa.String(512), nullable=False, server_default="")
        )


def downgrade():
    for table in ("ui_test_case_runs", "ui_test_suite_runs"):
        op.drop_column(table, "trace_path")
    op.drop_column("project_skill_spaces", "file_id")
