from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class Sprint(Base):
    __tablename__ = "sprints"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uk_sprint_project_name"),
        CheckConstraint("end_time > start_time", name="sprint_end_time_after_start_time"),
        {"comment": "项目迭代及计划时间；迭代状态由计划起止时间推导"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    sprint_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="迭代业务标识"
    )
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.project_id", name="fk_sprints_project_id", ondelete="RESTRICT"),
        nullable=False,
        comment="项目业务标识",
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="名称")
    description: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="业务描述"
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="迭代计划开始时间（UTC）"
    )
    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="迭代计划结束时间（UTC）"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
