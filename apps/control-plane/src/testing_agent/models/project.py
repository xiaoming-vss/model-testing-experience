from __future__ import annotations

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uk_project_user_name"),
        {"comment": "项目基本信息及当前所有者"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    project_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="项目业务标识"
    )
    user_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="当前项目所有者用户业务标识"
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="名称")
    description: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="业务描述"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
