"""Unified object storage file records."""

import sqlalchemy as sa

from alembic import op

revision = "20260927_0017"
down_revision = "20260926_0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stored_files",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
        ),
        *[
            sa.Column(name, sa.String(length), nullable=False)
            for name, length in [
                ("file_id", 64),
                ("project_id", 64),
                ("uploaded_by", 64),
                ("filename", 255),
                ("content_type", 128),
                ("sha256", 64),
                ("bucket", 255),
                ("object_key", 512),
                ("staging_key", 512),
                ("status", 20),
                ("purpose", 32),
                ("resource_type", 32),
                ("resource_id", 64),
            ]
        ],
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("file_id"),
    )
    op.create_index("ix_stored_files_project_id", "stored_files", ["project_id"])
    op.create_index("ix_stored_files_expires_at", "stored_files", ["expires_at"])
    op.add_column(
        "requirements",
        sa.Column("document_file_id", sa.String(64), nullable=False, server_default=""),
    )


def downgrade():
    op.drop_column("requirements", "document_file_id")
    op.drop_table("stored_files")
