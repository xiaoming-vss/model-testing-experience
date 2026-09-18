from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class ApiExtractRule(Base):
    __tablename__ = "api_extract_rules"
    __table_args__ = (
        UniqueConstraint("case_id", "var_key", name="uk_case_extract_var"),
        Index("idx_case_extract_order", "case_id", "order_no"),
    )
    id: Mapped[IdPk]
    extract_rule_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    case_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("api_cases.case_id", name="fk_api_extract_rules_case_id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    source_expr: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    var_key: Mapped[str] = mapped_column(String(120), nullable=False)
    default_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
