from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class ApiEnvironment(Base):
    __tablename__ = "api_environments"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uk_api_environment_project_name"),
        {"comment": "项目 API 测试环境及基础地址"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    environment_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="API 环境业务标识"
    )
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "projects.project_id", name="fk_api_environments_project_id", ondelete="RESTRICT"
        ),
        nullable=False,
        comment="项目业务标识",
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="名称")
    base_url: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="服务或环境基础地址"
    )
    description: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="业务描述"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否为所在作用域的默认项"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
