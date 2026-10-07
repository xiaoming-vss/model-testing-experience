from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class FunctionTestSuite(Base):
    __tablename__ = "function_test_suites"
    __table_args__ = (
        UniqueConstraint("requirement_id", "name", name="uk_function_suite_requirement_name"),
        {"comment": "需求下的功能测试集"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    suite_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="功能测试集业务标识"
    )
    requirement_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("requirements.requirement_id", name="fk_function_test_suites_requirement"),
        nullable=False,
        comment="需求业务标识",
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="名称")
    description: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="业务描述"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
