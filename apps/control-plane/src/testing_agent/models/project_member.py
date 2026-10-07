from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk


class ProjectMember(Base):
    """Non-owner membership; Project.user_id is the single source of ownership."""

    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uk_project_member"),
        CheckConstraint("role IN ('member', 'viewer', 'developer')", name="project_member_role"),
        Index("ix_project_members_user_project", "user_id", "project_id"),
        {"comment": "项目成员及项目内角色"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.project_id", ondelete="CASCADE"),
        nullable=False,
        comment="项目业务标识",
    )
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        comment="用户业务标识",
    )
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="项目内角色：owner/member/viewer/developer"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
