from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk


class StoredFile(Base):
    __tablename__ = "stored_files"
    __table_args__ = {"comment": "统一文件元数据及对象存储上传、完成和业务关联状态"}
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    file_id: Mapped[str] = mapped_column(String(64), unique=True, comment="统一文件业务标识")
    project_id: Mapped[str] = mapped_column(String(64), index=True, comment="项目业务标识")
    uploaded_by: Mapped[str] = mapped_column(String(64), comment="上传者用户业务标识")
    filename: Mapped[str] = mapped_column(String(255), comment="原始文件名")
    content_type: Mapped[str] = mapped_column(String(128), comment="文件 MIME 类型")
    size: Mapped[int] = mapped_column(BigInteger, comment="文件大小，单位字节")
    sha256: Mapped[str] = mapped_column(String(64), comment="文件内容 SHA-256 摘要")
    bucket: Mapped[str] = mapped_column(String(255), comment="对象存储桶名称")
    object_key: Mapped[str] = mapped_column(String(512), comment="已完成文件的对象存储键")
    staging_key: Mapped[str] = mapped_column(String(512), comment="上传暂存对象的存储键")
    status: Mapped[str] = mapped_column(
        String(20), default="pending", comment="文件状态：pending/ready/attached/archived/deleting"
    )
    purpose: Mapped[str] = mapped_column(String(32), comment="文件业务用途")
    resource_type: Mapped[str] = mapped_column(
        String(32), default="", comment="已关联的业务资源类型"
    )
    resource_id: Mapped[str] = mapped_column(String(64), default="", comment="已关联的业务资源标识")
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="文件完成上传确认时间（UTC）"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime, index=True, comment="有效期或清理期限截止时间（UTC）"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
