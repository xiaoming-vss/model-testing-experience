"""Direct attempts for independently managed requirement-generation stages."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt

CONTENT = Text().with_variant(LONGTEXT(), "mysql")


class AiGenerationAttempt(Base):
    __tablename__ = "ai_generation_attempts"
    __table_args__ = (
        UniqueConstraint("stage_id", "attempt_no", name="uq_generation_attempt_sequence"),
        UniqueConstraint("stage_id", "worker_task_id", name="uq_generation_attempt_worker"),
        Index("idx_generation_attempt_worker", "worker_task_id"),
        Index("idx_generation_attempt_status_id", "status", "id"),
        Index(
            "idx_generation_attempt_execution_stage_no", "execution_id", "stage_id", "attempt_no"
        ),
        {"comment": "AI 任务稳定阶段的生成、修订或人工编辑尝试及其输入输出"},
    )
    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="阶段生成或编辑尝试业务标识"
    )
    stage_id: Mapped[str] = mapped_column(
        ForeignKey("ai_generation_stages.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属稳定阶段业务标识",
    )
    execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_executions.execution_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="所属 AI 执行业务标识；人工编辑及迁移前的尝试为空",
    )
    attempt_no: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="同一稳定阶段内尝试序号"
    )
    operation: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="生成、修订或编辑操作类型"
    )
    worker_task_id: Mapped[str | None] = mapped_column(
        String(64), comment="关联 AI Worker 队列任务标识"
    )
    requested_by: Mapped[str | None] = mapped_column(
        String(64), comment="发起本次尝试的用户业务标识"
    )
    input_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), comment="本次生成或编辑的冻结输入快照"
    )
    revision_instruction: Mapped[str | None] = mapped_column(Text, comment="本次修订指令")
    status: Mapped[str] = mapped_column(String(20), nullable=False, comment="本次尝试的执行状态")
    output_content: Mapped[str | None] = mapped_column(
        CONTENT, comment="本次尝试输出的阶段候选正文"
    )
    output_format: Mapped[str | None] = mapped_column(String(20), comment="候选正文格式")
    output_context_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), comment="候选正文及来源的扩展上下文"
    )
    error_message: Mapped[str | None] = mapped_column(Text, comment="执行失败时的错误信息")
    review_status: Mapped[str | None] = mapped_column(
        String(20), comment="独立执行此候选的审核状态；需求链和无需审核时为空"
    )
    reviewer_user_id: Mapped[str | None] = mapped_column(
        String(64), comment="独立执行此候选的审核人业务标识；未审核为空"
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="独立执行此候选的审核时间（UTC）；未审核为空"
    )
    review_comment: Mapped[str | None] = mapped_column(
        Text, comment="独立执行此候选的审核意见；未审核为空"
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="候选因依赖失效的时间（UTC）"
    )
    invalidated_reason: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="候选失效原因；空字符串表示未记录"
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="尝试开始时间（UTC）"
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="尝试结束时间（UTC）"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="尝试创建时间（UTC）")
