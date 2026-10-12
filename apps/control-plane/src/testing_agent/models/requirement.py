from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class Requirement(Base):
    __tablename__ = "requirements"
    __table_args__ = (
        UniqueConstraint("sprint_id", "name", name="uk_requirement_sprint_name"),
        {"comment": "迭代需求及需求文档，文件通过统一文件记录管理"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    requirement_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="需求业务标识"
    )
    sprint_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sprints.sprint_id", name="fk_requirements_sprint"),
        nullable=False,
        comment="迭代业务标识",
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, comment="名称")
    document_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="text", comment="需求文档类型"
    )
    document_content: Mapped[str] = mapped_column(
        LONGTEXT, nullable=False, default="", comment="需求文档正文或提取内容"
    )
    document_file_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", comment="需求文档关联的统一文件业务标识"
    )
    document_filename: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", comment="需求文档原始文件名"
    )
    document_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, default="", comment="需求文档内容摘要"
    )
    document_download_url: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="历史文档下载地址元数据；不用于文件交付"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
