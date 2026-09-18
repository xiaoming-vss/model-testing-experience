from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk


class WorkerTask(Base):
    __tablename__ = "worker_tasks"
    __table_args__ = (
        UniqueConstraint("domain", "task_id", name="uk_worker_domain_task"),
        Index("idx_worker_domain_status_created", "domain", "status", "created_at"),
    )
    id: Mapped[IdPk]
    domain: Mapped[str] = mapped_column(String(10), nullable=False)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    # Compatibility payload attributes; never persisted in the queue.
    suite_id = None
    case_id = None
    collection_run_id = None
    collection_id = None
    generate_task_id = None
    llm_connection_id = None
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    worker_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[CreatedAt]
