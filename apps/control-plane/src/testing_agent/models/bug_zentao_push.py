"""Durable creation attempt: a timeout must never cause a duplicate remote Bug."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class BugZentaoPush(Base):
    __tablename__ = "bug_zentao_pushes"
    __table_args__ = {"comment": "本地 Bug 的禅道创建关联及正文同步账本"}
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    bug_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("bugs.bug_id", ondelete="CASCADE"),
        unique=True,
        comment="平台 Bug 业务标识",
    )
    operation_id: Mapped[str] = mapped_column(
        String(64), comment="远端写入操作标识，用于结果核对与避免重复写入"
    )
    actor_user_id: Mapped[str] = mapped_column(
        String(64), comment="本次操作人用户业务标识；外部调用使用其本人授权"
    )
    service_id: Mapped[str] = mapped_column(String(64), comment="项目共享服务业务标识")
    instance_url: Mapped[str] = mapped_column(String(512), comment="规范化的外部实例地址")
    status: Mapped[str] = mapped_column(
        String(20), comment="禅道创建状态：not_pushed/preparing/creating/succeeded/failed/unknown"
    )
    remote_bug_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="禅道实例内的远端 Bug 编号"
    )
    target_json: Mapped[dict[str, Any]] = mapped_column(JSON, comment="冻结的禅道创建目标 JSON")
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, comment="冻结的禅道创建请求内容 JSON"
    )
    error_message: Mapped[str] = mapped_column(
        String(512), default="", comment="执行或同步错误信息"
    )
    description_status: Mapped[str] = mapped_column(
        String(20),
        default="none",
        server_default="none",
        comment="禅道正文同步状态：none/pending/syncing/succeeded/failed/unknown",
    )
    description_operation_id: Mapped[str] = mapped_column(
        String(64), default="", server_default="", comment="禅道正文同步操作标识"
    )
    description_sync_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        server_default=text("('{}')"),
        comment="禅道正文同步的基线、映射及结果 JSON",
    )
    description_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="正文同步账本最近更新时间（UTC）"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
