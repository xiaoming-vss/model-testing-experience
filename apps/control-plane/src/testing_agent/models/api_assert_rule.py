from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class ApiAssertRule(Base):
    __tablename__ = "api_assert_rules"
    __table_args__ = (
        UniqueConstraint("case_id", "name", name="uk_case_assert_name"),
        Index("idx_case_assert_order", "case_id", "order_no"),
    )
    id: Mapped[IdPk]
    assert_rule_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    case_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("api_cases.case_id", name="fk_api_assert_rules_case_id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assert_source: Mapped[str] = mapped_column(String(30), nullable=False)
    target_expr: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    comparator: Mapped[str] = mapped_column(String(30), nullable=False)
    expected_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
