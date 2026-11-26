"""Shared identity for one AI execution across its stage attempts."""

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt


class AiExecution(Base):
    __tablename__ = "ai_executions"
    __table_args__ = (
        Index("idx_ai_execution_task_created", "task_id", "created_at", "execution_id"),
        {"comment": "AI 任务的一次执行身份及发起者"},
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
    created_at: Mapped[CreatedAt] = mapped_column(comment="执行创建时间（UTC）")
