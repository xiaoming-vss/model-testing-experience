"""Reference UI source archives through unified S3 file records."""

import sqlalchemy as sa

from alembic import op

revision = "20260927_0018"
down_revision = "20260927_0017"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ai_generate_task_source_archives",
        sa.Column("file_id", sa.String(64), nullable=False, server_default=""),
    )


def downgrade():
    op.drop_column("ai_generate_task_source_archives", "file_id")
