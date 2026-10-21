"""Lease file cleanup without holding a database transaction over storage calls."""

import sqlalchemy as sa

from alembic import op

revision = "20261021_0047"
down_revision = "20261021_0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stored_files",
        sa.Column(
            "cleanup_id",
            sa.String(64),
            nullable=False,
            server_default="",
            comment="当前清理领取代次；空表示未领取",
        ),
    )
    op.add_column(
        "stored_files",
        sa.Column(
            "cleanup_until",
            sa.DateTime(),
            nullable=True,
            comment="清理领取租约截止时间（UTC）；超时可由其他实例接管",
        ),
    )
    op.create_index(
        "ix_stored_file_cleanup", "stored_files", ["bucket", "status", "expires_at", "id"]
    )
    op.create_index("ix_stored_file_object", "stored_files", ["bucket", "object_key"])


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM stored_files WHERE cleanup_id <> ''")):
        raise RuntimeError("Stop and drain file cleanup before downgrade")
    op.drop_index("ix_stored_file_object", table_name="stored_files")
    op.drop_index("ix_stored_file_cleanup", table_name="stored_files")
    op.drop_column("stored_files", "cleanup_until")
    op.drop_column("stored_files", "cleanup_id")
