from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class ApiApp(Base):
    if TYPE_CHECKING:
        # 列表聚合计数；由 repository 批量写入，不对应表字段。
        interface_count: int
        enabled_interface_count: int

    __tablename__ = "api_apps"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uk_api_app_project_name"),
        Index("idx_api_app_project_enabled", "project_id", "enabled", "name"),
        {"comment": "项目级接口应用及可选代码仓库、base path 配置"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    app_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="接口应用业务标识"
    )
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.project_id", name="fk_api_apps_project", ondelete="RESTRICT"),
        nullable=False,
        comment="所属项目业务标识",
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="应用名称，同一项目内唯一"
    )
    description: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="应用用途说明"
    )
    base_path: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        default="",
        comment="应用级 URL 路径前缀；空字符串表示无前缀",
    )
    repository_project_id: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="",
        comment="关联 GitLab 仓库的远端项目标识；空字符串表示未关联",
    )
    repository_path: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        default="",
        comment="GitLab 仓库完整命名空间路径快照，例如 commerce/order-service",
    )
    repository_name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", comment="GitLab 仓库名称快照"
    )
    repository_instance_url: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        default="",
        comment="GitLab 实例规范化地址；不包含凭据",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="应用是否启用；不影响所属接口的独立状态",
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="乐观并发版本；应用信息每次更新加一"
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="创建应用的用户业务标识，仅用于追溯，不代表应用私有归属",
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
