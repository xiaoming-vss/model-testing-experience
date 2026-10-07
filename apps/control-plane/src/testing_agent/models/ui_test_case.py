from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class UiTestCase(Base):
    __tablename__ = "ui_test_cases"
    __table_args__ = (
        UniqueConstraint("suite_id", "name", name="uk_ui_case_suite_name"),
        Index("idx_ui_test_cases_suite_order", "suite_id", "order_no"),
        {"comment": "UI 测试用例及可执行步骤"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    case_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="测试用例业务标识"
    )
    suite_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "ui_test_suites.suite_id", name="fk_ui_test_cases_suite_id", ondelete="RESTRICT"
        ),
        nullable=False,
        comment="所属 UI 测试套件业务标识",
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, comment="名称")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用")
    order_no: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="执行或展示顺序"
    )
    steps_json: Mapped[list[Any]] = mapped_column(
        JSON, nullable=False, comment="可执行 UI 步骤列表 JSON"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
