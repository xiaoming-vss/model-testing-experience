"""An attachment upload is independent of the remote Bug creation attempt."""

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class BugZentaoAttachment(Base):
    __tablename__ = "bug_zentao_attachments"
    __table_args__ = (
        UniqueConstraint("bug_id", "file_id", name="uk_bug_zentao_attachment"),
        {"comment": "Bug 附件在指定禅道实例和远端 Bug 下的上传映射及操作账本"},
    )

    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    bug_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("bugs.bug_id", ondelete="CASCADE"), comment="平台 Bug 业务标识"
    )
    file_id: Mapped[str] = mapped_column(String(64), comment="统一文件业务标识")
    sha256: Mapped[str] = mapped_column(String(64), comment="文件内容 SHA-256 摘要")
    instance_url: Mapped[str] = mapped_column(String(512), comment="规范化的外部实例地址")
    remote_bug_id: Mapped[int] = mapped_column(Integer, comment="禅道实例内的远端 Bug 编号")
    remote_file_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="禅道实例内的远端附件编号"
    )
    operation_id: Mapped[str] = mapped_column(
        String(64), comment="远端写入操作标识，用于结果核对与避免重复写入"
    )
    actor_user_id: Mapped[str] = mapped_column(
        String(64), comment="本次操作人用户业务标识；外部调用使用其本人授权"
    )
    status: Mapped[str] = mapped_column(
        String(20), comment="禅道附件上传状态：pending/syncing/succeeded/failed/unknown"
    )
    error_message: Mapped[str] = mapped_column(
        String(512), default="", comment="执行或同步错误信息"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
