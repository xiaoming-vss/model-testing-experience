from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class Requirement(Base):
    __tablename__ = "requirements"
    __table_args__ = (UniqueConstraint("sprint_id", "name", name="uk_requirement_sprint_name"),)
    id: Mapped[IdPk]
    requirement_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    sprint_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sprints.sprint_id", name="fk_requirements_sprint"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    document_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    document_content: Mapped[str] = mapped_column(LONGTEXT, nullable=False, default="")
    document_filename: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    document_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    document_storage_path: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    document_download_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
