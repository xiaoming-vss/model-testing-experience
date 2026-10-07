"""Track recent Worker capabilities and immutable operation observations."""

import sqlalchemy as sa

from alembic import op

revision = "20261007_0033"
down_revision = "20261007_0032"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "integration_worker_presence",
        sa.Column("worker_id", sa.String(128), primary_key=True),
        sa.Column("runtime_generation", sa.String(64), nullable=False),
        sa.Column("protocol_versions", sa.JSON(), nullable=False),
        sa.Column("task_types", sa.JSON(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_integration_worker_presence_runtime",
        "integration_worker_presence",
        ["runtime_generation", "last_seen_at"],
    )
    op.create_index(
        "ix_integration_worker_presence_seen", "integration_worker_presence", ["last_seen_at"]
    )
    op.add_column("integration_jobs", sa.Column("first_claimed_at", sa.DateTime(), nullable=True))
    op.add_column("integration_jobs", sa.Column("queue_wait_ms", sa.BigInteger(), nullable=True))
    op.create_index(
        "ix_integration_jobs_project_created", "integration_jobs", ["project_id", "created_at"]
    )
    op.add_column(
        "integration_job_steps", sa.Column("remote_duration_ms", sa.Integer(), nullable=True)
    )
    for name in (
        "remote_recorded_at",
        "failed_at",
        "unknown_at",
        "lease_lost_at",
        "access_revoked_at",
    ):
        op.add_column("integration_job_steps", sa.Column(name, sa.DateTime(), nullable=True))
    op.create_index("ix_integration_job_steps_updated", "integration_job_steps", ["updated_at"])
    op.create_index(
        "ix_integration_job_steps_remote_recorded", "integration_job_steps", ["remote_recorded_at"]
    )


def downgrade():
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "SELECT COUNT(*) FROM integration_jobs WHERE recovery_required=1 OR status IN "
            "('queued','claimed','running','unknown','quarantined')"
        )
    ) or connection.scalar(
        sa.text(
            "SELECT COUNT(*) FROM integration_job_steps WHERE status IN ('write_intent','unknown')"
        )
    ):
        raise RuntimeError("集成任务未排空或仍待核对，禁止删除执行证据及其观测")
    op.drop_index("ix_integration_job_steps_remote_recorded", table_name="integration_job_steps")
    op.drop_index("ix_integration_job_steps_updated", table_name="integration_job_steps")
    for name in (
        "remote_duration_ms",
        "remote_recorded_at",
        "failed_at",
        "unknown_at",
        "lease_lost_at",
        "access_revoked_at",
    ):
        op.drop_column("integration_job_steps", name)
    op.drop_index("ix_integration_jobs_project_created", table_name="integration_jobs")
    op.drop_column("integration_jobs", "queue_wait_ms")
    op.drop_column("integration_jobs", "first_claimed_at")
    op.drop_table("integration_worker_presence")
