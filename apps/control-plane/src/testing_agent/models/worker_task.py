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
        Index("idx_worker_domain_lease", "domain", "status", "lease_expires_at", "id"),
        {"comment": "AI/API/UI Worker 执行队列及领取租约；集成任务使用独立队列"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    domain: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="Worker 任务域，用于区分 AI/API/UI 队列"
    )
    task_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="所属任务业务标识；与任务域组成唯一键"
    )
    task_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Worker 执行任务类型"
    )
    run_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False, comment="运行业务标识"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="pending/queued/claimed/running/success/failed/error/canceled/skipped",
    )
    worker_id: Mapped[str] = mapped_column(
        String(120), nullable=False, default="", comment="领取或执行任务的 Worker 标识"
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True, comment="当前执行租约到期时间（UTC）"
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="当前领取的最近心跳时间（UTC）"
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="执行开始时间（UTC）"
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="执行结束时间（UTC）"
    )
    error_message: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="执行或同步错误信息"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
