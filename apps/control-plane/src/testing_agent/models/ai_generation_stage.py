"""Stable identity and version allocation for a stage of a generation chain."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt


class AiGenerationStage(Base):
    __tablename__ = "ai_generation_stages"
    __table_args__ = (
        UniqueConstraint("task_id", "stage", name="uq_ai_generation_stage_task_stage"),
        {"comment": "需求生成链中稳定的阶段身份及下一个版本号"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="生成链阶段业务标识")
    task_id: Mapped[str] = mapped_column(
        ForeignKey("ai_generate_tasks.task_id", ondelete="CASCADE"),
        nullable=False,
        comment="所属生成链任务业务标识",
    )
    stage: Mapped[str] = mapped_column(String(40), nullable=False, comment="生成链阶段标识")
    next_version_no: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="本阶段下次审核通过时分配的版本号"
    )
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending", comment="稳定阶段当前候选审核状态"
    )
    current_attempt_id: Mapped[str | None] = mapped_column(
        String(64), comment="当前阶段候选尝试业务标识"
    )
    active_attempt_id: Mapped[str | None] = mapped_column(
        String(64), comment="当前正在执行的尝试业务标识"
    )
    source_batch_id: Mapped[str | None] = mapped_column(
        String(64), comment="UI 当前冻结输入批次标识；其他阶段为空"
    )
    source_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), comment="UI 当前输入批次来源快照；其他阶段为空"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
