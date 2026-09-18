from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class ApiCase(Base):
    __tablename__ = "api_cases"
    __table_args__ = (Index("idx_api_case_collection_order", "collection_id", "order_no"),)
    id: Mapped[IdPk]
    case_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    collection_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("api_collections.collection_id", name="fk_api_cases_collection"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    url_template: Mapped[str] = mapped_column(String(1024), nullable=False)
    headers_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    query_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    body_type: Mapped[str] = mapped_column(String(20), nullable=False, default="json")
    body_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON, nullable=True)
    body_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=5000)
    continue_on_failure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
