from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON, LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class PerfCase(Base):
    __tablename__ = "perf_cases"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uk_perf_case_project_name"),
        Index("idx_perf_cases_suite_order", "suite_id", "order_no"),
        {"comment": "项目性能测试用例及可执行 YAML"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    case_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="性能用例业务标识"
    )
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.project_id", name="fk_perf_cases_project_id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
        comment="项目业务标识",
    )
    suite_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("perf_suites.suite_id", name="fk_perf_cases_suite_id", ondelete="CASCADE"),
        index=True,
        nullable=True,
        comment="所属性能测试集业务标识；空值表示尚未归入测试集",
    )
    order_no: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="测试集内串行执行顺序"
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, comment="用例名称")
    description: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="业务描述"
    )
    yaml: Mapped[str] = mapped_column(
        Text().with_variant(LONGTEXT(), "mysql"),
        nullable=False,
        comment="YAML 用例正文；平台字段在发起运行时注入",
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="用例版本号，更新时递增"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用")
    data_files_json: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, comment="当前数据文件元数据 JSON，不含文件内容"
    )
    created_by: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="创建者用户业务标识"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")
