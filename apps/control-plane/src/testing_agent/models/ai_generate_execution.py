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
    __table_args__ = (UniqueConstraint("run_id", "stage"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("ai_generate_task_runs.run_id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(40))
    stage_order: Mapped[int] = mapped_column(Integer)
    execution_status: Mapped[str] = mapped_column(String(20), default="pending")
    review_status: Mapped[str] = mapped_column(String(20), default="pending")
    # Pointers are checked against the owning stage by the lifecycle module.
    # Avoid cyclic foreign keys so runs and their stages can be deleted atomically.
    current_artifact_attempt_id: Mapped[str | None] = mapped_column(String(64))
    active_attempt_id: Mapped[str | None] = mapped_column(String(64))
    reviewer_user_id: Mapped[str | None] = mapped_column(String(64))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class AiGenerateStageAttempt(Base):
    __tablename__ = "ai_generate_stage_attempts"
    __table_args__ = (
        UniqueConstraint("stage_id", "attempt_no", name="uq_ai_attempt_stage_number"),
        UniqueConstraint("stage_id", "worker_task_id", name="uq_ai_attempt_stage_worker"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    stage_id: Mapped[str] = mapped_column(
        ForeignKey("ai_generate_run_stages.id", ondelete="CASCADE"), nullable=False
    )
    attempt_no: Mapped[int] = mapped_column(Integer)
    operation: Mapped[str] = mapped_column(String(20))
    # worker_tasks.task_id is unique only within domain; this always means domain=ai.
    worker_task_id: Mapped[str | None] = mapped_column(String(64), index=True)
    requested_by: Mapped[str | None] = mapped_column(String(64))
    input_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    revision_instruction: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    output_content: Mapped[str | None] = mapped_column(CONTENT)
    output_context_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    output_format: Mapped[str | None] = mapped_column(String(20))
    progress_json: Mapped[Any | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    remediation: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[CreatedAt]


class AiGenerateRunImport(Base):
    __tablename__ = "ai_generate_run_imports"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("ai_generate_task_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    artifact_attempt_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_generate_stage_attempts.id"), nullable=True
    )
    imported_by: Mapped[str | None] = mapped_column(String(64))
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    imported_targets_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[CreatedAt]
