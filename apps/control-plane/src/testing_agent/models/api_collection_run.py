from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON, LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class ApiCollectionRun(Base):
    __tablename__ = "api_collection_runs"
    id: Mapped[IdPk]
    collection_run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    collection_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "api_collections.collection_id",
            name="fk_api_collection_runs_collection_id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )
    requirement_id = ""  # Response-only; resolved through current collection ownership.
    sprint_id = ""  # Response-only; resolved through current collection ownership.
    project_id = ""  # Response-only; resolved through current collection ownership.
    environment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    private_payload: Mapped[str | None] = mapped_column(
        Text().with_variant(LONGTEXT(), "mysql"), nullable=True
    )
    trigger_user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False, default="pending")
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runtime_vars_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class ApiCollectionRunItem(Base):
    __tablename__ = "api_collection_run_items"
    __table_args__ = (Index("idx_collection_run_item_order", "collection_run_id", "order_no"),)
    id: Mapped[IdPk]
    item_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    collection_run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "api_collection_runs.collection_run_id",
            name="fk_api_collection_run_items_collection_run_id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )
    case_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "api_cases.case_id", name="fk_api_collection_run_items_case_id", ondelete="CASCADE"
        ),
        index=True,
        nullable=False,
    )
    case_run_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("api_case_runs.run_id", name="fk_api_collection_run_items_case_run"),
        index=True,
        nullable=True,
    )
    order_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False, default="pending")
    continue_on_failure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
