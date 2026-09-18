"""Make resource identity independent of personal connections."""

import sqlalchemy as sa

from alembic import op

revision = "20260915_0004"
down_revision = "20260915_0003"
branch_labels = None
depends_on = None

KEY = [
    "provider",
    "local_resource_type",
    "local_resource_id",
    "remote_resource_type",
    "remote_resource_id",
]


def upgrade() -> None:
    with op.batch_alter_table("resource_bindings") as batch:
        batch.add_column(
            sa.Column("instance_url", sa.String(512), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column("instance_key", sa.String(64), nullable=False, server_default="")
        )
        batch.drop_constraint("uq_binding_resource", type_="unique")
        batch.create_unique_constraint("uq_binding_resource", ["instance_key", *KEY])


def downgrade() -> None:
    with op.batch_alter_table("resource_bindings") as batch:
        batch.drop_constraint("uq_binding_resource", type_="unique")
        batch.drop_column("instance_key")
        batch.drop_column("instance_url")
        batch.create_unique_constraint("uq_binding_resource", KEY)
