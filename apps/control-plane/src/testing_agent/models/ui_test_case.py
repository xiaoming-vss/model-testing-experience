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
    )
    id: Mapped[IdPk]
    case_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    suite_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "ui_test_suites.suite_id", name="fk_ui_test_cases_suite_id", ondelete="RESTRICT"
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    steps_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
