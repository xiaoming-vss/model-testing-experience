"""Index API collection run history by collection and creation order.

Revision ID: 20261114_0004
Revises: 20261114_0003
"""

from alembic import op

revision = "20261114_0004"
down_revision = "20261114_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_api_collection_run_latest",
        "api_collection_runs",
        ["collection_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_api_collection_run_latest", table_name="api_collection_runs")
