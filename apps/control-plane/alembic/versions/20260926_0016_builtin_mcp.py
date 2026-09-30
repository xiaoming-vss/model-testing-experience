"""Add built-in MCP template identity to shared services."""

import sqlalchemy as sa

from alembic import op

revision = "20260926_0016"
down_revision = "20260924_0015"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("shared_services") as batch:
        batch.add_column(sa.Column("template_id", sa.String(64), nullable=True))
        batch.create_unique_constraint(
            "uk_shared_service_template", ["project_id", "provider", "template_id"]
        )


def downgrade():
    with op.batch_alter_table("shared_services") as batch:
        batch.drop_constraint("uk_shared_service_template", type_="unique")
        batch.drop_column("template_id")
