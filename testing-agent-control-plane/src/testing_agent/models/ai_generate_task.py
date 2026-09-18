from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.mysql import JSON, LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt
from testing_agent.models.ai_run_view import AiRunView


class AiGenerateTask(Base):
    __tablename__ = "ai_generate_tasks"
    __table_args__ = (
        Index("ix_ai_generate_tasks_project_id", "project_id"),
        Index("ix_ai_generate_tasks_sprint_id", "sprint_id"),
        Index("ix_ai_generate_tasks_requirement_id", "requirement_id"),
        Index("ix_ai_generate_tasks_creator_user_id", "creator_user_id"),
    )
    id: Mapped[IdPk]
    task_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    task_type: Mapped[str] = mapped_column(
        String(50), index=True, nullable=False, default="api_case_generate"
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "projects.project_id", name="fk_ai_generate_tasks_project_id", ondelete="RESTRICT"
        ),
        nullable=False,
    )
    sprint_id: Mapped[str] = mapped_column(String(64), nullable=False)
    requirement_id: Mapped[str] = mapped_column(String(64), nullable=False)
    creator_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_content: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class AiGenerateTaskRun(AiRunView, Base):
    __tablename__ = "ai_generate_task_runs"
    id: Mapped[IdPk]
    run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    task_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "ai_generate_tasks.task_id", name="fk_ai_generate_task_runs_task_id", ondelete="CASCADE"
        ),
        index=True,
        nullable=False,
    )
    trigger_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    checkpoint_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    current_stage: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[CreatedAt]
