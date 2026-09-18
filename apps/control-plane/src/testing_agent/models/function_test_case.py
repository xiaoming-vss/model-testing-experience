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
    )
    id: Mapped[IdPk]
    case_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    suite_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "function_test_suites.suite_id",
            name="fk_function_test_cases_suite_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    module: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    priority: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    case_type: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    order_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    content_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=lambda: {"preconditions": [], "steps": []}
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
