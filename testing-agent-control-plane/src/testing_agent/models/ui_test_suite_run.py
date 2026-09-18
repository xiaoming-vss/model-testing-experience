from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class UiTestSuiteRun(Base):
    __tablename__ = "ui_test_suite_runs"
    id: Mapped[IdPk]
    suite_run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    suite_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "ui_test_suites.suite_id", name="fk_ui_test_suite_runs_suite_id", ondelete="CASCADE"
        ),
        index=True,
        nullable=False,
    )
    requirement_id = ""  # Response-only: derived from the current suite ownership.
    sprint_id = ""  # Response-only: derived from the current suite ownership.
    project_id = ""  # Response-only: derived from the current suite ownership.
    trigger_user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False, default="pending")
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class UiTestSuiteRunItem(Base):
    __tablename__ = "ui_test_suite_run_items"
    __table_args__ = (Index("idx_ui_suite_run_item_order", "suite_run_id", "order_no"),)
    id: Mapped[IdPk]
    item_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    suite_run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "ui_test_suite_runs.suite_run_id",
            name="fk_ui_test_suite_run_items_suite_run_id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )
    case_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "ui_test_cases.case_id", name="fk_ui_test_suite_run_items_case_id", ondelete="CASCADE"
        ),
        index=True,
        nullable=False,
    )
    order_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    continue_on_failure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False, default="pending")
    snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    step_results_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
