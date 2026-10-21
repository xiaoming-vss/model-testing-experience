"""Bound lease discovery by domain, active state and expiration."""

from alembic import op

revision = "20261021_0049"
down_revision = "20261021_0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_worker_domain_lease", "worker_tasks", ["domain", "status", "lease_expires_at", "id"]
    )


def downgrade() -> None:
    op.drop_index("idx_worker_domain_lease", table_name="worker_tasks")
