from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class ProjectSkillSpace(Base):
    __tablename__ = "project_skill_spaces"
    __table_args__ = (
        UniqueConstraint("scope_key", "filename", name="uk_skill_scope_name"),
        {"comment": "项目或全局技能文件集合及统一文件清单"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    skill_space_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="技能空间业务标识"
    )
    project_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey(
            "projects.project_id", name="fk_project_skill_spaces_project_id", ondelete="RESTRICT"
        ),
        nullable=True,
        index=True,
        comment="所属项目业务标识；空值表示全局技能包",
    )
    scope_key: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="技能文件作用域键，用于区分全局与项目"
    )
    filename: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="技能名称（兼容历史压缩包文件名）"
    )
    hash: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="技能文件清单的 SHA-256 摘要"
    )
    size_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, comment="技能清单中各文件大小之和，单位字节"
    )
    manifest: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="技能文件清单 JSON，包含路径、统一文件标识、大小及摘要",
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否为系统默认技能集合"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
