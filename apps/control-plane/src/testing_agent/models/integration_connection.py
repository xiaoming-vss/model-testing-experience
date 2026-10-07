from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class IntegrationConnection(Base):
    __tablename__ = "integration_connections"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", "name", name="uk_connection_user_provider_name"),
        Index("ix_integration_connections_project_id", "project_id"),
        {"comment": "用户个人外部服务连接及本人凭据"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    connection_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="个人授权连接业务标识"
    )
    project_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", comment="所属项目业务标识；个人独立连接可为空字符串"
    )
    user_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="个人连接及凭据所有者用户业务标识"
    )
    provider: Mapped[str] = mapped_column(
        String(30), index=True, nullable=False, comment="外部服务提供方类型"
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, comment="名称")
    base_url: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="服务或环境基础地址"
    )
    auth_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="", comment="外部服务认证方式"
    )
    account: Mapped[str] = mapped_column(
        String(120), nullable=False, default="", comment="外部服务登录账号"
    )
    secret_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="个人认证材料 JSON；其中密码等秘密按凭据加密规则存储"
    )
    access_token: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        comment="外部服务访问令牌或 API Key，存储形式随提供方认证方式而定",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        index=True,
        nullable=False,
        default="active",
        comment="个人连接认证状态：active/auth_failed",
    )
    last_auth_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近认证成功时间（UTC）"
    )
    last_auth_error: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="最近认证错误信息"
    )
    extra_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="提供方或绑定的扩展元数据 JSON"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
