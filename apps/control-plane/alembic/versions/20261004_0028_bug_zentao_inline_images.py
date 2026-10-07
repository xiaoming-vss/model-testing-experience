"""Persist inline image description updates separately from Bug creation."""

import sqlalchemy as sa

from alembic import op

revision = "20261004_0028"
down_revision = "20261004_0027"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("bug_zentao_pushes") as batch:
        batch.add_column(
            sa.Column("description_status", sa.String(20), nullable=False, server_default="none")
        )
        batch.add_column(
            sa.Column("description_operation_id", sa.String(64), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column(
                "description_sync_json", sa.JSON(), nullable=False, server_default=sa.text("('{}')")
            )
        )
        batch.add_column(sa.Column("description_updated_at", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("bug_zentao_pushes") as batch:
        for name in (
            "description_updated_at",
            "description_sync_json",
            "description_operation_id",
            "description_status",
        ):
            batch.drop_column(name)
