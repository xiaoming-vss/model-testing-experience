from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("auth_source", "external_id", name="uq_users_external_identity"),
        UniqueConstraint("super_admin_slot", name="uq_users_super_admin_slot"),
        {"comment": "平台注册用户及登录信息"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    user_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="用户业务标识"
    )
    nickname: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, comment="唯一登录昵称"
    )
    password: Mapped[str] = mapped_column(
        String(128), nullable=False, default="", comment="登录密码的 bcrypt 哈希"
    )
    email: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True, comment="用户邮箱；新注册必填，存量账号可待补填"
    )
    is_super_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否为系统预置的唯一超级管理员"
    )
    super_admin_slot: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="超级管理员唯一占位；普通用户为空"
    )
    auth_source: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="local",
        server_default="local",
        comment="认证来源：local/ldap；关联后不自动恢复本地身份",
    )
    external_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="LDAP 稳定身份 entryUUID；本地账号为空",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        index=True,
        comment="账号状态：active/disabled/pending_ldap",
    )
    disabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="账号被禁用的时间（UTC）"
    )
    disabled_reason: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="最近一次禁用原因"
    )
    disabled_by: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", comment="最近一次禁用操作人的用户业务标识"
    )
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否要求下次登录前修改密码"
    )
    password_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近一次密码修改或重置时间（UTC）"
    )
    token_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="令牌版本；递增后旧令牌全部失效"
    )
    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="连续登录失败次数"
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="登录失败锁定截止时间（UTC）"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
