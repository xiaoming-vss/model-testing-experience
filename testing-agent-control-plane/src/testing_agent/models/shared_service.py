"""Project-visible service configuration; credentials remain in personal connections."""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class SharedService(Base):
    __tablename__ = "shared_services"
    __table_args__ = (
        UniqueConstraint("project_id", "provider", "name", name="uk_shared_service_name"),
    )
    id: Mapped[IdPk]
    service_id: Mapped[str] = mapped_column(String(64), unique=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id"), index=True
    )
    provider: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(120))
    base_url: Mapped[str] = mapped_column(String(512))
    model_id: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class ServiceAuthorization(Base):
    __tablename__ = "service_authorizations"
    __table_args__ = (
        UniqueConstraint("service_id", "user_id", name="uk_service_authorization_user"),
    )
    id: Mapped[IdPk]
    service_id: Mapped[str] = mapped_column(String(64), ForeignKey("shared_services.service_id"))
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_id", ondelete="CASCADE")
    )
    connection_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("integration_connections.connection_id"), unique=True
    )
    created_at: Mapped[CreatedAt]
