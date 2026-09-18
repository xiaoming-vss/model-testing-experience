from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, IdPk


class AiGenerateTaskSourceArchive(Base):
    __tablename__ = "ai_generate_task_source_archives"
    id: Mapped[IdPk]
    archive_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    task_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "ai_generate_tasks.task_id",
            name="fk_ai_generate_task_source_archives_task_id",
            ondelete="CASCADE",
        ),
        unique=True,
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
