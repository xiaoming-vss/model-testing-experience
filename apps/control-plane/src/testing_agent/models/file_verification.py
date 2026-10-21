"""Durable ownership of private verification objects, including interrupted writers."""

from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk


class FileVerification(Base):
    __tablename__ = "file_verifications"
    __table_args__ = (
        Index("ix_file_verification_gc", "bucket", "state", "gc_after"),
        {"comment": "文件核验代次及未发布对象回收凭据；不随业务文件删除而级联丢失"},
    )
    id: Mapped[IdPk] = mapped_column(comment="核验记录数据库内部主键")
    operation_id: Mapped[str] = mapped_column(String(64), unique=True, comment="本次核验唯一代次")
    file_id: Mapped[str] = mapped_column(String(64), index=True, comment="对应统一文件业务标识")
    bucket: Mapped[str] = mapped_column(String(255), comment="本次核验目标存储桶")
    object_key: Mapped[str] = mapped_column(
        String(512), comment="本代次独占对象键；不得被其他代次复用"
    )
    state: Mapped[str] = mapped_column(
        String(20), comment="核验状态：running/published/discarded/abandoned"
    )
    deadline: Mapped[datetime] = mapped_column(
        DateTime, comment="允许发布本次核验结果的截止时间（UTC）"
    )
    settled_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="确认本次存储调用已经结束的时间；空表示仍可能晚到写入"
    )
    gc_after: Mapped[datetime] = mapped_column(
        DateTime, comment="下次可领取回收的时间（UTC）；未确认结束的对象持续巡检"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="核验领取时间（UTC）")
