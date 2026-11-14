from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class ApiInterface(Base):
    if TYPE_CHECKING:
        # 列表与详情响应附带的需求引用；由 repository 批量装配，不对应表字段。
        requirements: list[dict[str, str]]

    __tablename__ = "api_interfaces"
    __table_args__ = (
        UniqueConstraint("app_id", "method", "path_key", name="uk_api_interface_app_method_path"),
        Index("idx_api_interface_app_updated", "app_id", "updated_at", "id"),
        Index("idx_api_interface_updated", "updated_at", "id"),
        Index("idx_api_interface_method", "method"),
        {"comment": "项目接口定义及请求、响应结构"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    interface_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="接口定义业务标识"
    )
    app_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("api_apps.app_id", name="fk_api_interfaces_app", ondelete="RESTRICT"),
        nullable=False,
        comment="所属接口应用业务标识",
    )
    name: Mapped[str] = mapped_column(
        String(120), nullable=False, comment="接口名称，同一应用内不要求唯一"
    )
    method: Mapped[str] = mapped_column(String(10), nullable=False, comment="规范化大写 HTTP 方法")
    path: Mapped[str] = mapped_column(
        String(1024), nullable=False, comment="规范化相对路径，不包含应用 base path"
    )
    path_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="规范化路径的 SHA-256 十六进制摘要，用于身份唯一约束",
    )
    description: Mapped[str] = mapped_column(
        String(1024), nullable=False, default="", comment="接口用途、调用约束等说明"
    )
    tags_json: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, comment="标签字符串数组，导入和手工维护"
    )
    headers_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list, comment="请求头定义数组"
    )
    path_params_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list, comment="Path 参数定义数组"
    )
    query_params_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list, comment="Query 参数定义数组"
    )
    body_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="none", comment="请求体类型：none/json/form/raw"
    )
    body_schema_json: Mapped[Any | None] = mapped_column(
        JSON, nullable=True, comment="请求体 JSON Schema；无 schema 时为空"
    )
    body_example_json: Mapped[Any | None] = mapped_column(
        JSON, nullable=True, comment="请求体示例 JSON 值；无示例时为空"
    )
    body_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="Raw 请求体文本；仅 body_type=raw 时使用"
    )
    response_status: Mapped[int] = mapped_column(
        Integer, nullable=False, default=200, comment="默认成功响应状态码"
    )
    response_description: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="默认成功响应说明"
    )
    response_schema_json: Mapped[Any | None] = mapped_column(
        JSON, nullable=True, comment="响应 JSON Schema；无 schema 时为空"
    )
    response_example_json: Mapped[Any | None] = mapped_column(
        JSON, nullable=True, comment="响应示例 JSON 值；无示例时为空"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="接口是否启用；与应用状态独立"
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="乐观并发版本；接口内容或状态每次更新加一",
    )
    source_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="manual",
        comment="来源类型：manual/openapi_file；openapi_url 预留，本期不写入",
    )
    source_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        comment="来源文档标题或文件名；手工创建为空",
    )
    source_url: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        default="",
        comment="来源文档地址；本期恒为空，后续 URL 导入启用",
    )
    source_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", comment="来源文档 info.version"
    )
    source_imported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="最近一次由文档导入覆盖的时间（UTC）；手工创建为空",
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
