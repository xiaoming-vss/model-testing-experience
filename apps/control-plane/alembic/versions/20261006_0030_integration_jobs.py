"""Durable independent integration queue and transport receipts."""

import sqlalchemy as sa

from alembic import op

revision = "20261006_0030"
down_revision = "20261006_0029"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "integration_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(64), nullable=False),
        sa.Column("protocol_version", sa.Integer(), nullable=False),
        sa.Column("task_type", sa.String(40), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("bug_id", sa.String(64), nullable=False),
        sa.Column("actor_user_id", sa.String(64), nullable=False),
        sa.Column("service_id", sa.String(64), nullable=False),
        sa.Column("connection_id", sa.String(64), nullable=False),
        sa.Column("target_key", sa.String(64), nullable=False),
        sa.Column("runtime_generation", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("input_revision", sa.String(64), nullable=False),
        sa.Column("target_revision", sa.String(64), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("mapping_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("active_scope", sa.String(64), nullable=True),
        sa.Column("active_target", sa.String(64), nullable=True),
        sa.Column("worker_id", sa.String(128), nullable=False),
        sa.Column("claim_key", sa.String(64), nullable=True),
        sa.Column("claim_request_id", sa.String(64), nullable=False),
        sa.Column("claim_generation", sa.Integer(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
        sa.UniqueConstraint("actor_user_id", "request_id", name="uk_integration_job_request"),
        sa.UniqueConstraint("active_scope", name="uk_integration_job_active_scope"),
        sa.UniqueConstraint("active_target", name="uk_integration_job_active_target"),
        sa.UniqueConstraint("claim_key", name="uk_integration_job_claim_key"),
    )
    for name, columns in (
        ("ix_integration_jobs_queue", ["status", "created_at", "id"]),
        ("ix_integration_jobs_lease", ["status", "lease_expires_at"]),
        ("ix_integration_jobs_bug", ["project_id", "bug_id", "id"]),
    ):
        op.create_index(name, "integration_jobs", columns)
    op.create_table(
        "integration_job_steps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(64), nullable=False),
        sa.Column("step_key", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("dependencies_json", sa.JSON(), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("operation_id", sa.String(64), nullable=False),
        sa.Column("prepare_request_id", sa.String(64), nullable=False),
        sa.Column("intent_worker_id", sa.String(128), nullable=False),
        sa.Column("intent_generation", sa.Integer(), nullable=False),
        sa.Column("permit_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("receipts_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["job_id"], ["integration_jobs.job_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("job_id", "step_key", name="uk_integration_job_step"),
    )
    op.create_index(
        "ix_integration_job_steps_intent", "integration_job_steps", ["status", "updated_at"]
    )
    op.create_table(
        "integration_claim_receipts",
        sa.Column("claim_key", sa.String(64), nullable=False),
        sa.Column("worker_id", sa.String(128), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("job_id", sa.String(64), nullable=True),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("claim_key"),
        sa.ForeignKeyConstraint(["job_id"], ["integration_jobs.job_id"]),
    )
    op.create_index(
        "ix_integration_claim_receipts_job_id", "integration_claim_receipts", ["job_id"]
    )


def downgrade():
    # Dropping unresolved write evidence would make a subsequent deployment duplicate writes.
    connection = op.get_bind()
    unfinished = connection.scalar(
        sa.text(
            "SELECT COUNT(*) FROM integration_jobs WHERE status IN "
            "('queued', 'claimed', 'running', 'unknown')"
        )
    )
    unresolved = connection.scalar(
        sa.text(
            "SELECT COUNT(*) FROM integration_job_steps WHERE status IN ('write_intent', 'unknown')"
        )
    )
    if unfinished or unresolved:
        raise RuntimeError("集成任务尚未完成核对，禁止删除执行证据；回滚应用时保留加法迁移")
    op.drop_table("integration_claim_receipts")
    op.drop_table("integration_job_steps")
    op.drop_table("integration_jobs")
