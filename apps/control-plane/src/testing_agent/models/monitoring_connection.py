from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class MonitoringConnection(Base):
    __tablename__ = "monitoring_connections"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uk_monitoring_connection_project_name"),
        {"comment": "项目级 Prometheus/Grafana 监控接入及读写凭据"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    connection_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="监控接入业务标识"
    )
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "projects.project_id",
            name="fk_monitoring_connections_project_id",
            ondelete="RESTRICT",
        ),
        index=True,
        nullable=False,
        comment="项目业务标识",
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, comment="接入名称")
    query_url: Mapped[str] = mapped_column(
        String(1024), nullable=False, default="", comment="Prometheus 查询地址"
    )
    remote_write_url: Mapped[str] = mapped_column(
        String(1024), nullable=False, default="", comment="Prometheus Remote Write 地址"
    )
    query_auth_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="none",
        comment="查询认证方式：none/basic/bearer/headers",
    )
    query_secret_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="加密后的查询凭据 JSON"
    )
    remote_write_auth_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="none",
        comment="Remote Write 认证方式：none/basic/bearer/headers",
    )
    remote_write_secret_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="加密后的 Remote Write 凭据 JSON"
    )
    grafana_url: Mapped[str] = mapped_column(
        String(1024), nullable=False, default="", comment="Grafana 地址；空值表示未配置"
    )
    grafana_dashboard_uid: Mapped[str] = mapped_column(
        String(128), nullable=False, default="", comment="Grafana 看板 UID；空值表示未配置"
    )
    default_filters_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Grafana/Prometheus 默认筛选参数 JSON"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="是否允许发起新运行"
    )
    created_by: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="创建者用户业务标识"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
