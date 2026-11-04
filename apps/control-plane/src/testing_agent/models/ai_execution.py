"""Shared identity for one AI execution across its stage attempts."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt


class AiExecution(Base):
    __tablename__ = "ai_executions"
    __table_args__ = (
        Index("idx_ai_execution_task_created", "task_id", "created_at", "execution_id"),
        {"comment": "AI 任务的一次执行身份及发起者；独立多阶段执行保存聚合状态和初始输入"},
    )

    execution_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="AI 执行业务标识"
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("ai_generate_tasks.task_id", ondelete="CASCADE"),
        nullable=False,
        comment="所属 AI 任务业务标识",
    )
    requested_by: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="发起本次执行的用户业务标识"
    )
    workflow_status: Mapped[str | None] = mapped_column(
        String(20), comment="独立多阶段执行的聚合状态；单阶段执行为空并由尝试确定"
    )
    current_stage: Mapped[str | None] = mapped_column(
        String(40), comment="独立多阶段执行当前阶段；单阶段执行为空"
    )
    checkpoint_enabled: Mapped[bool | None] = mapped_column(
        Boolean, comment="独立多阶段执行是否启用人工检查点；单阶段执行为空"
    )
    trigger_type: Mapped[str | None] = mapped_column(
        String(30), comment="独立执行的触发方式；空值按历史默认方式处理"
    )
    source_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), comment="独立执行创建时冻结的业务输入快照 JSON"
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="独立多阶段执行开始时间（UTC）；未知为空"
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="独立多阶段执行结束时间（UTC）；未结束为空"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="执行创建时间（UTC）")
