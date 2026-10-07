"""Retain transport tombstones and persist restore quarantine."""

import sqlalchemy as sa

from alembic import op

revision = "20261007_0031"
down_revision = "20261006_0030"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "integration_jobs",
        sa.Column("recovery_required", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column("integration_jobs", sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_integration_jobs_retention",
        "integration_jobs",
        ["status", "archived_at", "finished_at", "id"],
    )
    op.create_table(
        "integration_runtime",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("restore_id", sa.String(64), nullable=False),
        sa.Column("runtime_generation", sa.String(64), nullable=False),
        sa.Column("worker_key_digest", sa.String(64), nullable=False),
        sa.Column("blocked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "SELECT COUNT(*) FROM integration_jobs WHERE status IN "
            "('queued','claimed','running','unknown','quarantined')"
        )
    ) or connection.scalar(
        sa.text(
            "SELECT COUNT(*) FROM integration_job_steps WHERE status IN ('write_intent','unknown')"
        )
    ):
        raise RuntimeError("集成任务尚未完成核对，禁止删除执行证据；回滚应用时保留加法迁移")
    if connection.scalar(sa.text("SELECT COUNT(*) FROM integration_runtime WHERE blocked=1")):
        raise RuntimeError("恢复环境尚未核对，禁止删除隔离标记")
    if connection.scalar(
        sa.text("SELECT COUNT(*) FROM integration_jobs WHERE recovery_required=1")
    ):
        raise RuntimeError("恢复任务尚未核对，禁止删除执行证据")
    op.drop_table("integration_runtime")
    op.drop_index("ix_integration_jobs_retention", table_name="integration_jobs")
    op.drop_column("integration_jobs", "archived_at")
    op.drop_column("integration_jobs", "recovery_required")
