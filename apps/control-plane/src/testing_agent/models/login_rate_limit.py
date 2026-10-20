from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, IdPk


class LoginRateLimit(Base):
    __tablename__ = "login_rate_limits"
    __table_args__ = (
        UniqueConstraint(
            "auth_method", "username", "client_ip", name="uk_login_rate_limit_method_name_ip"
        ),
        {"comment": "按用户名和客户端地址限制登录尝试频率"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    auth_method: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="local",
        server_default="local",
        comment="登录入口：local/ldap；隔离同名账号的失败限流",
    )
    username: Mapped[str] = mapped_column(String(50), nullable=False, comment="登录用户名")
    client_ip: Mapped[str] = mapped_column(String(64), nullable=False, comment="客户端 IP 地址")
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="当前时间窗口内的失败尝试次数"
    )
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="当前计数窗口开始时间（UTC）"
    )
    blocked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="限流封禁截止时间（UTC）"
    )
