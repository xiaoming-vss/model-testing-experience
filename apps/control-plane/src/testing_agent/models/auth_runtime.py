"""Persisted authentication cutover and reconciliation coordination (singleton)."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base


class AuthRuntime(Base):
    __tablename__ = "auth_runtime"
    __table_args__ = {"comment": "认证模式切换完成标记与 LDAP 对账协调"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="单例主键，固定为 1")
    mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="local", comment="已完成切换的认证模式：local/ldap"
    )
    fingerprint: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", comment="当前 LDAP 配置摘要；本地模式为空"
    )
    generation: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="认证配置切换代次，防止旧操作跨配置提交"
    )
    ldap_config: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="页面管理的 LDAP 配置；密码加密保存；空值表示尚未配置",
    )
    changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最后一次模式切换时间（UTC）"
    )
    reconcile_owner: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", comment="当前对账租约持有者；空值表示无人持有"
    )
    reconcile_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="对账租约截止时间（UTC）"
    )
