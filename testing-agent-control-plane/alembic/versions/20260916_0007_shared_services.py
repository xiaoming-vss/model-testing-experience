"""Separate project-visible service metadata from each member's personal authorization."""

import sqlalchemy as sa

from alembic import op

revision = "20260916_0007"
down_revision = "20260915_0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shared_services",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("service_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=False),
        sa.Column("model_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("service_id", name="uq_shared_services_service_id"),
        sa.UniqueConstraint("project_id", "provider", "name", name="uk_shared_service_name"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"]),
    )
    op.create_index("ix_shared_services_project_id", "shared_services", ["project_id"])
    op.create_table(
        "service_authorizations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("service_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("connection_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("service_id", "user_id", name="uk_service_authorization_user"),
        sa.UniqueConstraint("connection_id", name="uq_service_authorizations_connection_id"),
        sa.ForeignKeyConstraint(["service_id"], ["shared_services.service_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["integration_connections.connection_id"]),
    )


def downgrade():
    op.drop_table("service_authorizations")
    op.drop_table("shared_services")
