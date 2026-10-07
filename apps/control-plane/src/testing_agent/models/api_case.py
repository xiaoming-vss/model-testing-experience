from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class ApiCase(Base):
    __tablename__ = "api_cases"
    __table_args__ = (
        Index("idx_api_case_collection_order", "collection_id", "order_no"),
        {"comment": "API 测试用例及请求配置"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    case_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="测试用例业务标识"
    )
    collection_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("api_collections.collection_id", name="fk_api_cases_collection"),
        nullable=False,
        comment="API 集合业务标识",
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, comment="名称")
    description: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="业务描述"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用")
    order_no: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="执行或展示顺序"
    )
    method: Mapped[str] = mapped_column(String(10), nullable=False, comment="HTTP 请求方法")
    url_template: Mapped[str] = mapped_column(
        String(1024), nullable=False, comment="请求 URL 模板，可引用变量"
    )
    headers_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="请求头模板 JSON"
    )
    query_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="URL 查询参数模板 JSON"
    )
    body_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="json", comment="请求体类型"
    )
    body_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSON, nullable=True, comment="结构化请求体模板 JSON"
    )
    body_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="文本请求体模板"
    )
    timeout_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5000, comment="请求超时时间，单位毫秒"
    )
    continue_on_failure: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="失败后是否继续执行后续用例"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
