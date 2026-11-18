from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class PerfSuite(Base):
    __tablename__ = "perf_suites"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uk_perf_suite_project_name"),
        Index("idx_perf_suites_project_updated", "project_id", "updated_at"),
        {"comment": "项目级性能测试集，按顺序组织多条性能用例"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    suite_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="性能测试集业务标识"
    )
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.project_id", name="fk_perf_suites_project_id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
        comment="项目业务标识",
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, comment="测试集名称")
    description: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="业务描述"
    )
    created_by: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="创建者用户业务标识"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
