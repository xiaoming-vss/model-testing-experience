"""Persist readonly restore verification and explicit retained isolation."""

import sqlalchemy as sa

from alembic import op

revision = "20261007_0032"
down_revision = "20261007_0031"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "integration_restore_reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("review_id", sa.String(64), nullable=False, unique=True),
        sa.Column("restore_id", sa.String(64), nullable=False),
        sa.Column("scope_type", sa.String(10), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("actor_user_id", sa.String(64), nullable=True),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("state_digest", sa.String(64), nullable=False),
        sa.Column("facts_json", sa.JSON(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "restore_id", "scope_type", "scope_id", name="uk_integration_restore_scope"
        ),
    )
    op.create_index(
        "ix_integration_restore_project",
        "integration_restore_reviews",
        ["restore_id", "project_id", "decision"],
    )


def downgrade():
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT COUNT(*) FROM integration_restore_reviews")):
        raise RuntimeError("恢复核对证据必须保留，禁止删除执行证据")
    if connection.scalar(sa.text("SELECT COUNT(*) FROM integration_runtime WHERE blocked=1")):
        raise RuntimeError("恢复环境尚未核对，禁止删除隔离标记")
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
        raise RuntimeError("集成任务尚未完成核对，禁止删除执行证据")
    op.drop_table("integration_restore_reviews")
