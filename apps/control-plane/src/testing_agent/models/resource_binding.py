from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class ResourceBinding(Base):
    __tablename__ = "resource_bindings"
    __table_args__ = (
        Index(
            "idx_binding_shared_created",
            "local_resource_type",
            "local_resource_id",
            "created_at",
            "id",
        ),
        UniqueConstraint(
            "provider",
            "instance_key",
            "local_resource_type",
            "local_resource_id",
            "remote_resource_type",
            "remote_resource_id",
            name="uq_binding_resource",
        ),
        Index("idx_binding_connection", "connection_id", "status"),
        Index("idx_binding_local", "user_id", "local_resource_type", "local_resource_id", "status"),
        Index(
            "idx_binding_remote", "provider", "remote_resource_type", "remote_resource_id", "status"
        ),
        {"comment": "本地与外部资源的共享绑定；调用使用操作者本人授权"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    binding_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="资源绑定业务标识"
    )
    user_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
        comment="绑定创建或维护者用户业务标识，不代表绑定私有归属",
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False, comment="外部服务提供方类型")
    instance_url: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="规范化的外部实例地址"
    )
    instance_key: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", comment="规范化外部实例地址的摘要标识"
    )
    connection_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="建立或维护绑定时的个人连接标识；调用时重新解析操作者本人授权",
    )
    local_resource_type: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="本地资源类型"
    )
    local_resource_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="本地资源业务标识"
    )
    remote_resource_type: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="外部资源类型"
    )
    remote_resource_id: Mapped[str] = mapped_column(
        String(120), nullable=False, comment="外部资源标识"
    )
    remote_parent_id: Mapped[str] = mapped_column(
        String(120), nullable=False, default="", comment="外部父级资源标识"
    )
    remote_name_snapshot: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", comment="绑定时的外部资源名称快照"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", comment="绑定状态：active/unbound"
    )
    bound_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="资源绑定时间（UTC）"
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近验证外部资源时间（UTC）"
    )
    extra_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="提供方或绑定的扩展元数据 JSON"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
