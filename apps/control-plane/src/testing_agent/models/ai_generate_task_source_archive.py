from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, IdPk


class AiGenerateTaskSourceArchive(Base):
    __tablename__ = "ai_generate_task_source_archives"
    __table_args__ = {"comment": "AI 任务源代码压缩包及统一文件引用"}
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    archive_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="源代码压缩包业务标识"
    )
    task_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "ai_generate_tasks.task_id",
            name="fk_ai_generate_task_source_archives_task_id",
            ondelete="CASCADE",
        ),
        unique=True,
        nullable=False,
        comment="任务业务标识",
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False, comment="原始文件名")
    size_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="文件大小，单位字节"
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, comment="文件内容 SHA-256 摘要")
    file_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", comment="统一文件业务标识"
    )
    # Inert legacy metadata; source archives are delivered exclusively through S3.
    storage_path: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="历史压缩包路径元数据；文件交付使用统一文件标识"
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="上传时间（UTC）"
    )
