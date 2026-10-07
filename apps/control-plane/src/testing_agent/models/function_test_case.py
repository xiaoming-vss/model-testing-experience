from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class FunctionTestCase(Base):
    __tablename__ = "function_test_cases"
    __table_args__ = (
        UniqueConstraint("suite_id", "title", name="uk_function_case_suite_title"),
        Index("idx_function_case_suite_order", "suite_id", "order_no"),
        {"comment": "正式功能测试用例及结构化前置条件、步骤和预期"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    case_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        comment="固定用例编号；创建或导入时分配，落库后不因编辑改变",
    )
    suite_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "function_test_suites.suite_id",
            name="fk_function_test_cases_suite_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        comment="所属功能测试集业务标识",
    )
    module: Mapped[str] = mapped_column(
        String(120), nullable=False, default="", comment="功能用例所属业务模块"
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="标题")
    priority: Mapped[str] = mapped_column(String(30), nullable=False, default="", comment="优先级")
    case_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="", comment="用例类型"
    )
    order_no: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="执行或展示顺序"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")

    content_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: {"preconditions": [], "steps": []},
        comment="结构化功能用例内容，包含前置条件及步骤与对应预期",
    )

    def __init__(self, **kwargs):
        from testing_agent.domain.function_case_content import CaseContent, from_legacy

        legacy = {
            key: kwargs.pop(key, "") for key in ("preconditions", "steps", "expected_results")
        }
        content = kwargs.pop("content", None)
        stored_content = kwargs.pop("content_json", None)
        if content is None:
            content = stored_content
        kwargs["content_json"] = CaseContent.model_validate(
            content if content is not None else from_legacy(**legacy)
        ).model_dump()
        super().__init__(**kwargs)

    @property
    def content(self):
        return self.content_json

    @property
    def preconditions(self):
        from testing_agent.domain.function_case_content import legacy_fields

        return legacy_fields(self.content_json or {})["preconditions"]

    @property
    def steps(self):
        from testing_agent.domain.function_case_content import legacy_fields

        return legacy_fields(self.content_json or {})["steps"]

    @property
    def expected_results(self):
        from testing_agent.domain.function_case_content import legacy_fields

        return legacy_fields(self.content_json or {})["expected_results"]
