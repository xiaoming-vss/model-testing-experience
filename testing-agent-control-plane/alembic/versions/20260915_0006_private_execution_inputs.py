"""Separate encrypted API executor inputs from shared execution history."""

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGTEXT

from alembic import op

revision = "20260915_0006"
down_revision = "20260915_0005"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("api_case_runs", "api_collection_runs"):
        op.add_column(
            table,
            sa.Column(
                "private_payload", sa.Text().with_variant(LONGTEXT(), "mysql"), nullable=True
            ),
        )


def downgrade():
    for table in ("api_case_runs", "api_collection_runs"):
        op.drop_column(table, "private_payload")
