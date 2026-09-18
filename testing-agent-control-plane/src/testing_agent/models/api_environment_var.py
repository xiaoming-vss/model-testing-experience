from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class ApiEnvironmentVar(Base):
    __tablename__ = "api_environment_vars"
    __table_args__ = (UniqueConstraint("environment_id", "var_key", name="uk_api_env_var_key"),)
    id: Mapped[IdPk]
    env_var_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    environment_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "api_environments.environment_id",
            name="fk_api_environment_vars_environment_id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )
    var_key: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    secret_user_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
