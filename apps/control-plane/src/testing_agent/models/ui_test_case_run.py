from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class UiTestCaseRun(Base):
    __tablename__ = "ui_test_case_runs"
    id: Mapped[IdPk]
    run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    case_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "ui_test_cases.case_id", name="fk_ui_test_case_runs_case_id", ondelete="CASCADE"
        ),
        index=True,
        nullable=False,
    )
    suite_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    requirement_id = ""  # Response-only: derived from the current suite ownership.
    sprint_id = ""  # Response-only: derived from the current suite ownership.
    project_id = ""  # Response-only: derived from the current suite ownership.
    trigger_user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False, default="pending")
    snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    step_results_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
