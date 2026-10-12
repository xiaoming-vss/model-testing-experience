"""Normalized AI run lifecycle; legacy run columns are a transition projection."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, UpdatedAt

CONTENT = Text().with_variant(LONGTEXT(), "mysql")


class AiGenerateRunStage(Base):
    __tablename__ = "ai_generate_run_stages"
    __table_args__ = (
        UniqueConstraint("run_id", "stage"),
        {"comment": "AI 运行的阶段执行、人工审核及产物指针"},
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="AI 运行阶段主键标识")
    run_id: Mapped[str] = mapped_column(
        ForeignKey("ai_generate_task_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        comment="运行业务标识",
    )
    stage: Mapped[str] = mapped_column(String(40), comment="AI 阶段标识")
    stage_order: Mapped[int] = mapped_column(Integer, comment="AI 阶段执行顺序")
    execution_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        comment="AI 阶段执行状态：pending/running/completed/failed/waiting_review",
    )
    review_status: Mapped[str] = mapped_column(
        String(20), default="pending", comment="AI 阶段审核状态：pending/approved/rejected"
    )
    # Pointers are checked against the owning stage by the lifecycle module.
    # Avoid cyclic foreign keys so runs and their stages can be deleted atomically.
    current_artifact_attempt_id: Mapped[str | None] = mapped_column(
        String(64), comment="当前供审核或导入的阶段尝试标识"
    )
    active_attempt_id: Mapped[str | None] = mapped_column(
        String(64), comment="当前推进中的阶段尝试标识"
    )
    reviewer_user_id: Mapped[str | None] = mapped_column(
        String(64), comment="阶段审核人用户业务标识"
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="审核或核对时间（UTC）"
    )
    review_comment: Mapped[str | None] = mapped_column(Text, comment="阶段人工审核意见")
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")


class AiGenerateStageAttempt(Base):
    __tablename__ = "ai_generate_stage_attempts"
    __table_args__ = (
        UniqueConstraint("stage_id", "attempt_no", name="uq_ai_attempt_stage_number"),
        UniqueConstraint("stage_id", "worker_task_id", name="uq_ai_attempt_stage_worker"),
        {"comment": "AI 阶段的历次生成或修订尝试及输入、输出、进度"},
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="AI 阶段尝试主键标识")
    stage_id: Mapped[str] = mapped_column(
        ForeignKey("ai_generate_run_stages.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属 AI 运行阶段的主键标识",
    )
    attempt_no: Mapped[int] = mapped_column(Integer, comment="阶段内尝试序号")
    operation: Mapped[str] = mapped_column(String(20), comment="阶段尝试操作类型")
    # worker_tasks.task_id is unique only within domain; this always means domain=ai.
    worker_task_id: Mapped[str | None] = mapped_column(
        String(64), index=True, comment="AI 域 Worker 队列任务标识"
    )
    requested_by: Mapped[str | None] = mapped_column(String(64), comment="发起该尝试的用户业务标识")
    input_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, comment="阶段尝试冻结的输入快照 JSON"
    )
    revision_instruction: Mapped[str | None] = mapped_column(Text, comment="本次修订指令")
    status: Mapped[str] = mapped_column(String(20), comment="当前状态")
    output_content: Mapped[str | None] = mapped_column(CONTENT, comment="阶段尝试输出正文")
    output_context_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, comment="阶段尝试输出上下文 JSON"
    )
    output_format: Mapped[str | None] = mapped_column(String(20), comment="阶段尝试输出格式")
    progress_json: Mapped[Any | None] = mapped_column(JSON, comment="阶段尝试进度信息 JSON")
    error_message: Mapped[str | None] = mapped_column(Text, comment="执行或同步错误信息")
    remediation: Mapped[str | None] = mapped_column(Text, comment="失败后的处理建议")
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="执行开始时间（UTC）"
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="执行结束时间（UTC）"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")


class AiGenerateRunImport(Base):
    __tablename__ = "ai_generate_run_imports"
    __table_args__ = {"comment": "AI 运行产物导入正式资产的记录"}
    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="AI 导入记录主键标识")
    run_id: Mapped[str] = mapped_column(
        ForeignKey("ai_generate_task_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="运行业务标识",
    )
    imported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="正式资产导入时间（UTC）"
    )
    imported_targets_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, comment="已导入正式资产的类型和业务标识列表 JSON"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
