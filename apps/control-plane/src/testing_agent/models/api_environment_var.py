from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class ApiEnvironmentVar(Base):
    __tablename__ = "api_environment_vars"
    __table_args__ = (
        UniqueConstraint("environment_id", "var_key", name="uk_api_env_var_key"),
        {"comment": "API 环境变量及个人秘密变量归属"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    env_var_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="环境变量业务标识"
    )
    environment_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "api_environments.environment_id",
            name="fk_api_environment_vars_environment_id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
        comment="API 环境业务标识",
    )
    var_key: Mapped[str] = mapped_column(String(120), nullable=False, comment="变量名称")
    value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        comment="环境变量值；个人秘密变量由所属用户权限控制，对外展示脱敏",
    )
    description: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="业务描述"
    )
    secret_user_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
        comment="秘密变量所属用户业务标识；普通变量为空字符串",
    )
    is_secret: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否为个人秘密变量"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
