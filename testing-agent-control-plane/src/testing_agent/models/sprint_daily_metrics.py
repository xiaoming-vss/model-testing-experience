from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Date, Integer, String, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class SprintDailyMetrics(Base):
    __tablename__ = "sprint_daily_metrics"
    __table_args__ = (UniqueConstraint("sprint_id", "snapshot_date", name="uk_sprint_date"),)
    id: Mapped[IdPk]
    metric_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    sprint_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    function_case_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    function_case_executed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    function_case_pending: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    function_case_success: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    function_case_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    api_case_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    api_case_executed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    api_case_pending: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    api_case_success: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    api_case_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ui_case_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ui_case_executed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ui_case_pending: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ui_case_success: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ui_case_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bug_details_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    bug_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bug_resolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bug_closed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bug_unresolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bug_fatal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bug_serious: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bug_normal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bug_suggestion: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
