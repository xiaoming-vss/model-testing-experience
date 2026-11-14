"""Entry visualization bindings and batch receipts.

Revision ID: 20261114_0003
Revises: 20261113_0002
"""

import sqlalchemy as sa

from alembic import op

revision = "20261114_0003"
down_revision = "20261113_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_generate_tasks",
        sa.Column(
            "execution_entry_id",
            sa.String(64),
            nullable=False,
            server_default="",
            comment="单用例图解所属执行条目业务标识；其他任务为空字符串",
        ),
    )
    op.create_index(
        "ix_ai_generate_tasks_execution_entry_id", "ai_generate_tasks", ["execution_entry_id"]
    )
    op.create_table(
        "test_order_entry_visualizations",
        sa.Column(
            "id", sa.Integer(), primary_key=True, autoincrement=True, comment="数据库内部主键"
        ),
        sa.Column("entry_id", sa.String(64), nullable=False, comment="唯一所属执行条目业务标识"),
        sa.Column("task_id", sa.String(64), nullable=False, comment="本条目的稳定 AI 任务业务标识"),
        sa.Column(
            "effective_attempt_id",
            sa.String(64),
            nullable=True,
            comment="当前有效图解尝试标识；无可用图解时为空",
        ),
        sa.Column(
            "effective_snapshot_hash",
            sa.String(64),
            nullable=True,
            comment="有效图解输入正文 SHA-256；无有效产物时为空",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, comment="绑定创建时间（UTC）"
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="有效指针更新时间（UTC）",
        ),
        sa.ForeignKeyConstraint(["entry_id"], ["test_order_entries.entry_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["ai_generate_tasks.task_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["effective_attempt_id"], ["ai_generation_attempts.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("entry_id"),
        sa.UniqueConstraint("task_id"),
        comment="执行条目图解任务绑定及当前有效产物指针",
    )
    op.create_table(
        "test_order_visualization_batches",
        sa.Column(
            "id", sa.Integer(), primary_key=True, autoincrement=True, comment="数据库内部主键"
        ),
        sa.Column("batch_id", sa.String(64), nullable=False, comment="批次业务标识"),
        sa.Column("order_id", sa.String(64), nullable=False, comment="所属测试单业务标识"),
        sa.Column("actor_id", sa.String(64), nullable=False, comment="本次批量提交用户业务标识"),
        sa.Column("request_id", sa.String(64), nullable=False, comment="客户端幂等请求标识"),
        sa.Column(
            "signature", sa.String(64), nullable=False, comment="固定选择集合与模型连接请求摘要"
        ),
        sa.Column(
            "items",
            sa.JSON(),
            nullable=False,
            comment="逐条接收回执数组；含 entryId、disposition、runId 或安全错误",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, comment="批次提交时间（UTC）"
        ),
        sa.ForeignKeyConstraint(["order_id"], ["test_orders.order_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("batch_id"),
        sa.UniqueConstraint("actor_id", "request_id", name="uq_visualization_batch_request"),
        comment="手动批量图解接收回执；固定提交集合及逐条运行身份",
    )
    op.create_index(
        "ix_test_order_visualization_batches_order_id",
        "test_order_visualization_batches",
        ["order_id"],
    )


def downgrade() -> None:
    op.drop_table("test_order_visualization_batches")
    op.drop_table("test_order_entry_visualizations")
    op.drop_index("ix_ai_generate_tasks_execution_entry_id", table_name="ai_generate_tasks")
    op.drop_column("ai_generate_tasks", "execution_entry_id")
