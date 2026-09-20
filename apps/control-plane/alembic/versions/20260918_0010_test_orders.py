"""Test orders and their execution entries for manual functional testing."""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision = "20260918_0010"
down_revision = "20260917_0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "test_orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("sprint_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("tested_version", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id", name=op.f("uq_test_orders_order_id")),
        sa.UniqueConstraint("sprint_id", "name", name="uk_test_order_sprint_name"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_test_orders_project_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sprint_id"],
            ["sprints.sprint_id"],
            name="fk_test_orders_sprint_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_test_orders_project_id", "test_orders", ["project_id"])
    op.create_index("ix_test_orders_sprint_id", "test_orders", ["sprint_id"])
    op.create_table(
        "test_order_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entry_id", sa.String(64), nullable=False),
        sa.Column("order_id", sa.String(64), nullable=False),
        sa.Column("case_type", sa.String(20), nullable=False),
        sa.Column("case_id", sa.String(64), nullable=False),
        sa.Column("order_no", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", mysql.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("entry_id", name=op.f("uq_test_order_entries_entry_id")),
        sa.UniqueConstraint("order_id", "case_type", "case_id", name="uk_test_order_entry_case"),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["test_orders.order_id"],
            name="fk_test_order_entries_order_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_test_order_entries_case_id", "test_order_entries", ["case_id"])
    op.create_index("ix_test_order_entries_order_id", "test_order_entries", ["order_id"])
    op.create_index("ix_test_order_entries_status", "test_order_entries", ["status"])
    op.create_index(
        "idx_test_order_entry_order",
        "test_order_entries",
        ["order_id", "order_no"],
        unique=False,
    )


def downgrade():
    op.drop_table("test_order_entries")
    op.drop_table("test_orders")
