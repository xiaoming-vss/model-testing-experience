from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"comment": "平台注册用户及登录信息"}
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
        String(100), unique=True, nullable=True, comment="用户邮箱"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
