"""Freeze whole testcase push batches, including not-yet-issued operations."""

import sqlalchemy as sa

from alembic import op

revision = "20261021_0045"
down_revision = "20261021_0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "function_case_push_requests",
        sa.Column(
            "id", sa.Integer(), primary_key=True, autoincrement=True, comment="批次记录内部主键"
        ),
        sa.Column("actor_user_id", sa.String(64), nullable=False, comment="原批次发起用户业务标识"),
        sa.Column(
            "request_id", sa.String(64), nullable=False, comment="客户端批次编号；同一用户全局唯一"
        ),
        sa.Column("project_id", sa.String(64), nullable=False, comment="原批次所属项目业务标识"),
        sa.Column(
            "request_digest",
            sa.String(64),
            nullable=False,
            comment="原客户端参数和资源范围摘要；重试变更参数拒绝",
        ),
        sa.Column(
            "target_digest",
            sa.String(64),
            nullable=False,
            comment="原远端实例与目标摘要；绑定变化后不得重用批次",
        ),
        sa.Column(
            "manifest_json",
            sa.JSON(),
            nullable=False,
            comment="按用例编号冻结所属测试集和原内容摘要；不包含正文或凭据",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="批次首次提交时间（UTC）",
        ),
        sa.UniqueConstraint("actor_user_id", "request_id", name="uk_function_push_batch"),
        comment="功能用例推送批次原始选择及内容摘要；重试不自动纳入新增用例",
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM function_case_push_requests")):
        raise RuntimeError("Preserve testcase push batch receipts; downgrade refused")
    op.drop_table("function_case_push_requests")
