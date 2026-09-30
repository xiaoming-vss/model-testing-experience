from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class ProjectSkillSpace(Base):
    __tablename__ = "project_skill_spaces"
    __table_args__ = (UniqueConstraint("scope_key", "filename", name="uk_skill_scope_name"),)
    id: Mapped[IdPk]
    skill_space_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    project_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey(
            "projects.project_id", name="fk_project_skill_spaces_project_id", ondelete="RESTRICT"
        ),
        nullable=True,
        index=True,
    )
    scope_key: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    hash: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    manifest: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
