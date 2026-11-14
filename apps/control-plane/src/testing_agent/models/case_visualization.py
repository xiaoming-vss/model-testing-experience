"""Entry-owned auxiliary visualization pointers and immutable batch receipts."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class TestOrderEntryVisualization(Base):
    __tablename__ = "test_order_entry_visualizations"
    __table_args__ = {"comment": "执行条目图解任务绑定及当前有效产物指针"}
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    entry_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("test_order_entries.entry_id", ondelete="CASCADE"),
        unique=True,
        comment="唯一所属执行条目业务标识",
    )
    task_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ai_generate_tasks.task_id", ondelete="CASCADE"),
        unique=True,
        comment="本条目的稳定 AI 任务业务标识",
    )
    effective_attempt_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_generation_attempts.id", ondelete="SET NULL"),
        nullable=True,
        comment="当前有效图解尝试标识；无可用图解时为空",
    )
    effective_snapshot_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="有效图解输入正文 SHA-256；无有效产物时为空",
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="绑定创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="有效指针更新时间（UTC）")


class TestOrderVisualizationBatch(Base):
    __tablename__ = "test_order_visualization_batches"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_id", name="uq_visualization_batch_request"),
        {"comment": "手动批量图解接收回执；固定提交集合及逐条运行身份"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    batch_id: Mapped[str] = mapped_column(String(64), unique=True, comment="批次业务标识")
    order_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("test_orders.order_id", ondelete="CASCADE"),
        index=True,
        comment="所属测试单业务标识",
    )
    actor_id: Mapped[str] = mapped_column(String(64), comment="本次批量提交用户业务标识")
    request_id: Mapped[str] = mapped_column(String(64), comment="客户端幂等请求标识")
    signature: Mapped[str] = mapped_column(String(64), comment="固定选择集合与模型连接请求摘要")
    items: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        comment="逐条接收回执数组；含 entryId、disposition、runId 或安全错误",
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="批次提交时间（UTC）")
