from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class ApiAssertRule(Base):
    __tablename__ = "api_assert_rules"
    __table_args__ = (
        UniqueConstraint("case_id", "name", name="uk_case_assert_name"),
        Index("idx_case_assert_order", "case_id", "order_no"),
        {"comment": "API 用例的有序响应断言规则"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    assert_rule_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="断言规则业务标识"
    )
    case_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("api_cases.case_id", name="fk_api_assert_rules_case_id", ondelete="CASCADE"),
        nullable=False,
        comment="测试用例业务标识",
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, comment="名称")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用")
    order_no: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="执行或展示顺序"
    )
    assert_source: Mapped[str] = mapped_column(String(30), nullable=False, comment="断言数据来源")
    target_expr: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="断言目标提取表达式"
    )
    comparator: Mapped[str] = mapped_column(String(30), nullable=False, comment="断言比较运算符")
    expected_value: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="断言预期值"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
