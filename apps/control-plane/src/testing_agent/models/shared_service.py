"""Project-visible service configuration; credentials remain in personal connections."""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class SharedService(Base):
    __tablename__ = "shared_services"
    __table_args__ = (
        UniqueConstraint("project_id", "provider", "name", name="uk_shared_service_name"),
        {"comment": "项目成员共同可见的服务配置；个人凭据另存于个人连接"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    service_id: Mapped[str] = mapped_column(String(64), unique=True, comment="项目共享服务业务标识")
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id"), index=True, comment="项目业务标识"
    )
    provider: Mapped[str] = mapped_column(String(30), comment="外部服务提供方类型")
    name: Mapped[str] = mapped_column(String(120), comment="名称")
    base_url: Mapped[str] = mapped_column(String(512), comment="服务或环境基础地址")
    template_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="内置服务模板标识"
    )
    model_id: Mapped[str] = mapped_column(String(255), default="", comment="LLM 模型标识")
    zentao_instance_url: Mapped[str] = mapped_column(
        String(512), default="", comment="禅道业务实例地址，用于区分 MCP 服务与禅道目标"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")


class ServiceAuthorization(Base):
    __tablename__ = "service_authorizations"
    __table_args__ = (
        UniqueConstraint("service_id", "user_id", name="uk_service_authorization_user"),
        {"comment": "项目共享服务与成员本人授权连接的关联"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    service_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("shared_services.service_id"), comment="项目共享服务业务标识"
    )
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_id", ondelete="CASCADE"), comment="用户业务标识"
    )
    connection_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("integration_connections.connection_id"),
        unique=True,
        comment="个人授权连接业务标识",
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
